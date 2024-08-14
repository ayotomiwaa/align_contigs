document.getElementById('contigForm').addEventListener('submit', processContigs);
document.getElementById("exampleButton").addEventListener('click', loadExample);

function loadExample() {
    document.getElementById('sra').value = 'ERR2756788';
    document.getElementById('contig').value = "ERR2756788_1, ERR2756788_2";
}

async function processContigs(event) {

    event.preventDefault();

    const sra = document.getElementById('sra').value.trim().replace(/^>/, '');
    const contigInput = document.getElementById('contig').value.trim();
    const resultsDiv = document.getElementById('results');

    // if (!sra || !contigInput) {
    //     resultsDiv.innerHTML = 'Please enter both SRA and Contig IDs.';
    //     return;
    // }
    // Input validation
    if (!sra) {
      displayError("Please enter an SRA value.");
      return;
    }

    if (contigInput.length === 0) {
        displayError("Please enter at least one contig ID.");
        return;
    }

    resultsDiv.innerHTML = 'Processing... Please wait.';

    try {
        const contigIds = contigInput.replace(/\s/g, '').split(',');
        const response = await fetch(
        'http://127.0.0.1:5500/process_contigs',
        {
            method: 'POST',
            headers: {
            'Content-Type': 'application/json'
            },
            body: JSON.stringify({ SRA: sra, contig: contigIds }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.error) {
          throw new Error(data.error);
        }

        if (!data || data.length === 0) {
          resultsDiv.innerHTML = '<p class="no-results"> No contigs found. </p>';
        } else {
          displayResults(data);
        }
      
          // const results = await response.json();
          // displayResults(results);


      } catch (error) {
        console.error('Fetch error:', error);
        if (error.message.includes('No contigs found')) {
          resultsDiv.innerHTML = '<p class="no-results">No contigs found. </p>';
        } else {
          displayError(`An error occured: ${error.message}`);
        }
        // resultsDiv.innerHTML = `Error: ${error.message}`;
      }
}

function displayResults(results) {
    // console.log('Raw results:', results);

    const resultsDiv = document.getElementById('results');
    if (!results || results.length === 0) {
      resultsDiv.innerHTML = '<p>No results found.</p>';
      return;
  }

  // Get the keys from the first result object
  const keys = Object.keys(results[0]);

  let tableHtml = `
      <h2>Diamond Analysis Results</h2>
      <div class="table-container">
          <table class="results-table">
              <thead>
                  <tr>
                      ${keys.map(key => `<th>${key}</th>`).join('')}
                  </tr>
              </thead>
              <tbody>
  `;

  results.forEach(result => {
      tableHtml += '<tr>';
      keys.forEach(key => {
          tableHtml += `<td>${result[key] || 'N/A'}</td>`;
      });
      tableHtml += '</tr>';
  });

  tableHtml += `
              </tbody>
          </table>
      </div>
  `;

  resultsDiv.innerHTML = tableHtml;
}

function displayError(message) {
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = `<p class="error">${message}</p>`;
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelector('button').addEventListener('click', processContigs);
});