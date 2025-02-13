from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import subprocess
import os
import tempfile
import logging
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
import time
import requests
import gc


app = Flask(__name__, static_folder='static')
CORS(app)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class LoganContigsFetcher:
    """
    Handles retrieval and processing of Logan Contigs data using AWS CLI
    """
    S3_BUCKET = "s3://logan-pub/c"
    
    def __init__(self, temp_dir=None):
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Verify required tools are installed"""
        try:
            # Check AWS CLI
            subprocess.run(['aws', '--version'], 
                         capture_output=True, check=True)
            # Check zstd
            subprocess.run(['zstd', '--version'], 
                         capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError("Required tools (aws-cli, zstd) not installed")
    
    def fetch_assembly(self, sra_id):
        """
        Fetch and decompress assembly for an SRA accession using AWS CLI
        """
        logger.info(f"Fetching assembly for {sra_id}")
        
        # Setup paths
        compressed_file = os.path.join(self.temp_dir, f"{sra_id}.contigs.fa.zst")
        decompressed_file = os.path.join(self.temp_dir, f"{sra_id}.contigs.fa")
        
        try:
            # Download using AWS CLI
            s3_path = f"{self.S3_BUCKET}/{sra_id}/{sra_id}.contigs.fa.zst"
            if not self._aws_download(s3_path, compressed_file):
                return None
            
            # Decompress
            if not self._decompress_file(compressed_file, decompressed_file):
                return None
            
            # Read and validate assembly
            with open(decompressed_file, 'r') as f:
                assembly_data = f.read()
            
            if self._validate_assembly(assembly_data, sra_id):
                return assembly_data
            return None
            
        except Exception as e:
            logger.error(f"Error processing {sra_id}: {str(e)}")
            return None
        finally:
            self._cleanup_files(compressed_file, decompressed_file)
    
    def _aws_download(self, s3_path, output_file):
        """
        Download file using AWS CLI
        """
        try:
            logger.info(f"Downloading from {s3_path}")
            start_time = time.time()
            
            cmd = [
                'aws', 's3', 'cp',
                s3_path,
                output_file,
                '--no-sign-request',
                '--quiet'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"AWS CLI download failed: {result.stderr}")
                return False
            
            duration = time.time() - start_time
            size = os.path.getsize(output_file)
            logger.info(f"Download completed: {size} bytes in {duration:.2f}s")
            return True
            
        except subprocess.SubprocessError as e:
            logger.error(f"AWS CLI error: {str(e)}")
            return False
    
    def _decompress_file(self, input_file, output_file):
        """
        Decompress zstd file
        """
        try:
            logger.info(f"Decompressing {input_file}")
            start_time = time.time()
            
            cmd = ['zstd', '-d', input_file, '-o', output_file, '-f']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Decompression failed: {result.stderr}")
                return False
            
            duration = time.time() - start_time
            size = os.path.getsize(output_file)
            logger.info(f"Decompression completed: {size} bytes in {duration:.2f}s")
            return True
            
        except subprocess.SubprocessError as e:
            logger.error(f"Decompression error: {str(e)}")
            return False
    
    def _validate_assembly(self, assembly_data, sra_id):
        """
        Validate assembly format and content
        """
        if not assembly_data:
            logger.error("Empty assembly data")
            return False
        
        if not assembly_data.startswith('>'):
            logger.error("Invalid FASTA format")
            return False
        
        lines = assembly_data.split('\n')
        headers = [line for line in lines if line.startswith('>')]
        
        if not headers:
            logger.error("No FASTA headers found")
            return False
        
        # Validate header format
        for header in headers[:5]:
            if not header.startswith(f'>{sra_id}_'):
                logger.error(f"Invalid header format: {header}")
                return False
            if 'ka:f:' not in header or 'L:' not in header:
                logger.error(f"Missing metadata in header: {header}")
                return False
        
        logger.info(f"Assembly validated: {len(headers)} contigs")
        return True
    
    def _cleanup_files(self, *files):
        """Clean up temporary files"""
        for file in files:
            try:
                if os.path.exists(file):
                    os.remove(file)
            except OSError as e:
                logger.warning(f"Failed to remove {file}: {str(e)}")

def create_protein_db(sequence, header, temp_dir):
    """
    Create Diamond database from protein sequence
    """
    db_file = os.path.join(temp_dir, 'protein_query_db')
    query_file = os.path.join(temp_dir, 'query.fasta')
    
    try:
        # Validate protein sequence
        valid_aa = set('ACDEFGHIKLMNPQRSTVWY')
        if not all(aa.upper() in valid_aa for aa in sequence):
            logger.error("Invalid protein sequence")
            return None
        
        # Write protein sequence
        with open(query_file, 'w') as f:
            f.write(f">{header}\n")
            for i in range(0, len(sequence), 60):
                f.write(sequence[i:i+60] + '\n')
        
        # Create Diamond database
        cmd = [
            'diamond', 'makedb',
            '--in', query_file,
            '-d', db_file,
            '--threads', '4'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Failed to create Diamond database: {result.stderr}")
            return None
        
        if not os.path.exists(f"{db_file}.dmnd"):
            logger.error("Diamond database file not created")
            return None
        
        logger.info(f"Created Diamond database: {os.path.getsize(f'{db_file}.dmnd')} bytes")
        return db_file
        
    except Exception as e:
        logger.error(f"Error creating protein database: {str(e)}")
        return None

def search_assembly(assembly_data, sra_id, db_file, temp_dir):
    """
    Search DNA assembly against protein database using BLASTX
    """
    assembly_file = os.path.join(temp_dir, f'{sra_id}_assembly.fasta')
    output_file = os.path.join(temp_dir, f'{sra_id}_results.pro')
    
    try:
        with open(assembly_file, 'w') as f:
            f.write(assembly_data)
        
        cmd = [
            "diamond", "blastx",
            "-q", assembly_file,
            "-d", f"{db_file}.dmnd",
            "--sensitive",
            "--masking", "0",
            "-f", "6",
            "qseqid", "qstart", "qend", "qlen", "qstrand",
            "sseqid", "sstart", "send", "slen",
            "pident", "evalue", "cigar",
            "qseq_translated", "sseq",
            "-o", output_file,
            # "--max-target-seqs", "5",
            # "--evalue", "1e-3",
            # "--min-score", "50",
            # "--threads", "4"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Diamond BLASTX failed: {result.stderr}")
            return None
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            with open(output_file) as f:
                content = f.read()
                hit_count = len(content.splitlines())
                logger.info(f"Found {hit_count} alignments for {sra_id}")
                return content
        else:
            logger.warning(f"No alignments found for {sra_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error during Diamond search: {str(e)}")
        return None

def process_sra_parallel(sra_id, sequence, header, temp_dir):
    """Process a single SRA accession"""
    
    try:
        with tempfile.TemporaryDirectory() as process_temp_dir:
            fetcher = LoganContigsFetcher(process_temp_dir)
            assembly = fetcher.fetch_assembly(sra_id)
            if not assembly:
                return sra_id, None
            
            db_file = create_protein_db(sequence, header, process_temp_dir)
            if not db_file:
                return sra_id, None
            
            # Run BLASTX search on full assembly
            results = search_assembly(assembly, sra_id, db_file, process_temp_dir)
            gc.collect()  # Force garbage collection
            
            return sra_id, results

    except Exception as e:
        logger.error(f"Error processing {sra_id}: {str(e)}")
        return sra_id, None

def run_diamond_analysis(sequence, header, srr_accessions, max_workers=8):
    """
    Main analysis workflow with parallel processing
    """
    results = {}
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Process SRAs in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_sra = {
                executor.submit(
                    process_sra_parallel, sra, sequence, header, temp_dir
                ): sra for sra in srr_accessions
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_sra):
                sra_id, result = future.result()
                if result:
                    results[sra_id] = result
    
    return results

@app.route('/process_sequence', methods=['POST'])
def process_sequence():
    """
    Handle sequence processing request
    """
    try:
        data = request.json
        sequence = data.get('sequence', '').strip()
        header = data.get('header', 'query').strip()
        srr_accessions = data.get('srr_accessions', [])
        
        if not sequence:
            return jsonify({'error': 'Missing sequence'}), 400
        
        if not srr_accessions:
            return jsonify({'error': 'No SRR accessions provided'}), 400
        
        # Convert string input to list if necessary
        if isinstance(srr_accessions, str):
            srr_accessions = [acc.strip() for acc in srr_accessions.split('\n') if acc.strip()]
        
        logger.info(f"Processing request with {len(srr_accessions)} SRR accessions")
        results = run_diamond_analysis(sequence, header, srr_accessions)
        
        if not results:
            return jsonify({'message': 'No alignments found'}), 200
        
        return jsonify(results), 200
        
    except Exception as e:
        logger.exception("Error processing request")
        return jsonify({'error': str(e)}), 500

# @app.route('/')
# def serve_index():
#     """Serve the main HTML page"""
#     return send_from_directory('static', 'index.html')
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)