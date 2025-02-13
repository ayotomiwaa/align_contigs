document.getElementById('processSequence').addEventListener('click', processSequence);
document.getElementById('loadExample').addEventListener('click', loadExample);


async function processSequence(event) {

        
    event.preventDefault();

    const sequenceInput = document.getElementById('sequence');
    const srrInput = document.getElementById('srr_accessions');
    const resultsDiv = document.getElementById('results');

    if (!sequenceInput || !srrInput) {
        displayError("Cannot find input elements.");
        return;
    }

    const fullSequence = sequenceInput.value.trim();
    const srrAccessions = srrInput.value.trim();

    if (!fullSequence) {
        displayError("Please enter a protein sequence.");
        return;
    }

    // Split the input into header and sequence
    const lines = fullSequence.split('\n');
    const header = lines[0].startsWith('>') ? lines[0].substring(1) : '';
    const sequence = lines.slice(1).join('').replace(/\s/g, '');

    // Process comma-separated SRR accessions
    const srrList = srrAccessions 
        ? srrAccessions.split(',')
            .map(acc => acc.trim())
            .filter(acc => acc) : [];
        //     .filter(acc => acc && acc.toUpperCase().startsWith('SRR'))
        // : [];

    if (srrAccessions && srrList.length === 0) {
        displayError("Please enter valid SRR accessions (e.g., SRR1234567)");
        return;
    }

    resultsDiv.innerHTML = '<p>Processing... Please wait.</p>';

    try {
        const response = await fetch('/process_sequence', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                sequence: sequence,
                header: header,
                srr_accessions: srrList
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        displayResults(data);
    } catch (error) {
        console.error('Fetch error:', error);
        displayError(`An error occurred: ${error.message}`);
    }
}


function displayResults(results) {
    const resultsDiv = document.getElementById('results');
    
    if (!results || Object.keys(results).length === 0) {
        resultsDiv.innerHTML = '<p class="no-results">No alignments found.</p>';
        return;
    }

    let resultsHtml = '<h2>Alignment Results</h2>';

    for (const [sra, alignments] of Object.entries(results)) {
        resultsHtml += `
            <div class="sra-section">
                <h3>Results for ${sra}</h3>
                <div class="table-container">
                    <table class="results-table">
                        <thead>
                            <tr>
                                <th>Query</th>
                                <th>qstart</th>
                                <th>qend</th>
                                <th>qlen</th>
                                <th>strand</th>
                                <th>Subject</th>
                                <th>sstart</th>
                                <th>send</th>
                                <th>slen</th>
                                <th>%id</th>
                                <th>E-value</th>
                                <th>Query Sequence</th>
                                <th>Translated Sequence</th>
                            </tr>
                        </thead>
                        <tbody>`;

        // Split alignments into lines if it's a string
        const lines = typeof alignments === 'string' ? alignments.split('\n') : [alignments];
        
        // Process each line
        lines.forEach(line => {
            if (line.trim()) {
                const fields = line.split(/\s+/);
                if (fields.length >= 13) {
                    resultsHtml += `
                        <tr>
                            <td>${fields[0]}</td>
                            <td>${fields[1]}</td>
                            <td>${fields[2]}</td>
                            <td>${fields[3]}</td>
                            <td>${fields[4]}</td>
                            <td>${fields[5]}</td>
                            <td>${fields[6]}</td>
                            <td>${fields[7]}</td>
                            <td>${fields[8]}</td>
                            <td>${fields[9]}</td>
                            <td>${fields[10]}</td>
                            <td class="sequence-cell">${fields[11]}</td>
                            <td class="sequence-cell">${fields[12]}</td>
                        </tr>`;
                }
            }
        });

        resultsHtml += `
                    </tbody>
                </table>
            </div>
        </div>`;
    }

    resultsDiv.innerHTML = resultsHtml;
}
function displayError(message) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.innerHTML = `<p class="error">${message}</p>`;
}

function loadExample() {
  const sequenceInput = document.getElementById('sequence');
  const srrInput = document.getElementById('srr_accessions');

  sequenceInput.value = `>Test_Sequence
  MTKQTVKPGHFNQEFYEFLKGKGFFNEGSSLTLKHFFFAQKDDAAIKDFD
  FYRYNRTTMLDICQARVAYKVVTHYFDCYEGGCISAKDVVVTNLNKSAGY
  PLNKLGKAGLYYESLSYDEQDHLYALTKRNILPTMTQLNLKYAISGKERA
  RTVGGVSLLSTMTTRQFHQKHLKSIVNTRNATVVIGTTKFYGGWDNMLNT
  LISGVENPCLMGWDYPKCDRALPSMIRMISAMILGSKHVTCCTASDKYYR
  LCNELAQVLTEVVYSNGGFYFKPGGTTSGDATTAYANSVFNIFQAVSANI
  NRLLTVDSYAIHNESVKSLQRQLYDNCYRATSVDATFVSDYYQFLRKHFS
  MMILSDDGVVCYNKDYADMGYVADIGAFKAALYYQNNVFMSTAKCWVETD
  LSKGPHEFCSQHTLQIVDQDGKYYLPYPDPSRIISAGVFVDDVAKTDSVV
  LLERYVSLAIDAYPLSKHPDPEYQKVFYTMLEWVKHLTKTLHQGILETFS
  VTLLEDASSKFWTESFYAGLYEKSTLLQSAGLCVVCSSQTVLRCGDCLRR
  PLLCTKCAYDHVVSTDHKFILSITPYVCNASGCSVNDVTQLFLGGLSYYC
  KDHKPQ`;

  srrInput.value = 'ERR2756788, ERR2756789, ERR2756790, ERR2756791';

}