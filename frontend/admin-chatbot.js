// ==========================================================================
// Loopline — Admin AI Chatbot page logic
// Requires config.js, admin.js loaded first.
// ==========================================================================

function addChatMessage(text, role, meta) {
  const history = document.getElementById('chat-history');
  const el = document.createElement('div');
  el.className = `admin-chat-msg ${role}`;

  if (role === 'bot' && typeof marked !== 'undefined') {
    // Bot responses come from Gemini and may contain markdown
    // (bold, numbered lists, inline code, etc.) - render as HTML.
    // User messages use textContent (never innerHTML) — XSS guard:
    // a customer complaint text should never be interpreted as markup.
    const mdContainer = document.createElement('div');
    mdContainer.className = 'chat-md';
    mdContainer.innerHTML = marked.parse(text || '');
    el.appendChild(mdContainer);
  } else {
    el.textContent = text;
  }

  if (meta && role === 'bot') {
    if (meta.sources && meta.sources.length) {
      const src = document.createElement('span');
      src.className = 'rag-sources';
      src.textContent = `Sources: ${meta.sources.join(', ')}`;
      el.appendChild(src);
    }
    const badge = document.createElement('span');
    badge.className = 'rag-badge';
    badge.textContent = meta.used_rag ? '● Answered via Gemini + Qdrant (RAG)' : '○ Fallback response (RAG not configured or unavailable)';
    el.appendChild(badge);
  }

  history.appendChild(el);
  history.scrollTop = history.scrollHeight;
  return el;
}

async function checkTicketScope(ticketNo) {
  const statusEl = document.getElementById('ticket-scope-status');
  if (!ticketNo) { statusEl.textContent = ''; return; }
  try {
    // Reuse the admin complaints list filter to confirm the ticket exists
    // and show a quick preview - avoids a dedicated GET-by-id endpoint.
    const data = await adminFetch(`/admin/complaints?search=${ticketNo}&page_size=1`);
    const match = data.items.find(i => i.ticket_no === Number(ticketNo));
    statusEl.style.color = match ? 'var(--teal-dark)' : 'var(--red)';
    statusEl.textContent = match ? `✓ ${match.category} · ${match.priority} priority` : 'No complaint found with that ticket #';
  } catch (e) {
    statusEl.textContent = '';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const session = adminGuardAndWireNav();
  if (!session) return;

  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const ticketInput = document.getElementById('ticket-scope');

  ticketInput.addEventListener('change', () => checkTicketScope(ticketInput.value.trim()));

  async function send() {
    const question = input.value.trim();
    if (!question) return;
    addChatMessage(question, 'user');
    input.value = '';
    sendBtn.disabled = true;

    const typingEl = addChatMessage('…', 'bot');

    try {
      const ticketNo = ticketInput.value.trim();
      const body = { question };
      if (ticketNo) body.ticket_no = Number(ticketNo);

      const result = await adminFetch('/admin/chatbot/ask', { method: 'POST', body: JSON.stringify(body) });
      typingEl.remove();
      addChatMessage(result.answer, 'bot', { sources: result.sources, used_rag: result.used_rag });
    } catch (err) {
      typingEl.remove();
      addChatMessage(err.message || 'Something went wrong asking the chatbot.', 'bot', { used_rag: false });
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
});
