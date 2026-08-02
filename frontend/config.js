// ==========================================================================
// Loopline — shared frontend config
// Include this BEFORE auth.js / script.js / admin*.js on every page.
// ==========================================================================

// Defaults to the local dev backend (see ../backend/README.md - run with
// `uvicorn app.main:app --reload`, defaults to port 8000). Change this one
// line once the API is deployed for real (see docs/DEPLOYMENT.md) - nothing
// else in the frontend needs to change.
const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.hostname === '')
  ? 'http://127.0.0.1:8000'
  : 'https://REPLACE-WITH-YOUR-DEPLOYED-API-URL.onrender.com';
