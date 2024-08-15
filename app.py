from flask import Flask, request, jsonify, send_from_directory
#from flask_cors import CORS
import subprocess
import os
import tempfile
import requests

app = Flask(__name__)
CORS(app)

@app.route('/process_contigs', methods=['POST'])
def process_contigs():
    data = request.json
    sra = data.get('SRA')
    contig_ids = data.get('contig')

    # Fetch FASTA data from the logan_get_contig API
    fasta_data = fetch_contigs(sra, contig_ids)

    # Process the FASTA data with Diamond
    results = run_diamond_analysis(fasta_data)

    return jsonify(results)

def fetch_contigs(sra, contig_ids):
    url = 'https://ag63ar36qwfndxxfc32b3w57oy0wcugc.lambda-url.us-east-1.on.aws/'
    payload = {'SRA': sra, 'contig': contig_ids}
    headers = {'Authorization': 'Bearer 20240522', 'Content-Type': 'application/json'}

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.text

def run_diamond_analysis(fasta_data):
    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = os.path.join(temp_dir, 'input.fasta')
        db_file = os.path.join(temp_dir, 'db')
        output_file = os.path.join(temp_dir, 'output.tsv')

        # Write FASTA data to input file
        with open(input_file, 'w') as f:
            f.write(fasta_data)

        # Create Diamond database
        subprocess.run(['diamond', 'makedb', '--in', input_file, '-d', db_file], check=True)

        # Align the contigs against the database
        subprocess.run(['diamond', 'blastp', '-q', input_file, '-d', db_file, '-o', output_file, '--sensitive'], check=True)

        # Read and parse results
        results = []
        with open(output_file, 'r') as f:
            for line in f:
                fields = line.strip().split('\t')
                # results.append(fields)
                results.append({
                    'Query': fields[0],
                    'Subject': fields[1],
                    'Identity': fields[2],
                    'Alignment length': fields[3],
                    'E-value': fields[10]
                })

    return results


@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5500)
