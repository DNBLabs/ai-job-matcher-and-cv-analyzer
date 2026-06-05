/**
 * Root React component for the Job Seeker dashboard SPA.
 */

import "./App.css";

function App() {
  return (
    <main className="app-shell">
      <header>
        <h1>AI Job Matcher &amp; CV Analyzer</h1>
        <p>
          Upload CVs, run UK job searches, and review Match Scores with Interview
          Likelihood estimates.
        </p>
      </header>
      <p className="status-note">Sign-in and dashboard flows arrive in Task 20.</p>
    </main>
  );
}

export default App;
