/**
 * RandomWeb — Frontend Application Logic
 * Handles random redirect, search, submission, and real-time counter.
 */

// ─── Configuration ──────────────────────────────────────────
const API_BASE = '/api';

// Supabase client will be initialized after fetching config from backend
let supabaseClient = null;

// ─── DOM Elements ───────────────────────────────────────────
const randomBtn = document.getElementById('random-btn');
const btnText = randomBtn.querySelector('.btn-text');
const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');
const submitForm = document.getElementById('submit-form');
const submitInput = document.getElementById('submit-input');
const submitBtn = document.getElementById('submit-btn');
const submitFeedback = document.getElementById('submit-feedback');
const counterValue = document.getElementById('counter-value');
const headerActiveCount = document.getElementById('header-active-count');
const toastContainer = document.getElementById('toast-container');

// ─── State ──────────────────────────────────────────────────
let currentCount = 0;
let targetCount = 0;
let animationFrame = null;
let searchDebounceTimer = null;

// ─── Utility Functions ──────────────────────────────────────
function openInNewTab(url) {
  // Use a temporary anchor element — works reliably inside iframes
  // where window.open() is blocked by sandbox/CSP
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function formatNumber(num) {
  if (num >= 1_000_000) {
    return (num / 1_000_000).toFixed(2) + 'M';
  }
  if (num >= 1_000) {
    return (num / 1_000).toFixed(1) + 'K';
  }
  return num.toLocaleString();
}

function formatNumberFull(num) {
  return num.toLocaleString();
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-exiting');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ─── Animated Counter ───────────────────────────────────────
function animateCounter(target) {
  targetCount = target;

  if (animationFrame) {
    cancelAnimationFrame(animationFrame);
  }

  const startCount = currentCount;
  const diff = target - startCount;
  const duration = Math.min(1500, Math.max(300, Math.abs(diff) * 10));
  const startTime = performance.now();

  function step(timestamp) {
    const elapsed = timestamp - startTime;
    const progress = Math.min(elapsed / duration, 1);

    // Ease-out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    currentCount = Math.round(startCount + diff * eased);

    counterValue.textContent = formatNumberFull(currentCount);

    if (progress < 1) {
      animationFrame = requestAnimationFrame(step);
    } else {
      currentCount = target;
      counterValue.textContent = formatNumberFull(target);
    }
  }

  animationFrame = requestAnimationFrame(step);
}

// ─── Fetch Stats (Initial) ─────────────────────────────
async function fetchStats() {
  try {
    const response = await fetch(`${API_BASE}/stats`);
    if (response.ok) {
      const data = await response.json();
      
      // Update header with total indexed count (sites indexed)
      if (data.total_count !== undefined) {
        headerActiveCount.textContent = formatNumber(data.total_count);
      }
      
      // Update footer with active count (animated)
      const activeCount = data.active_count || 0;
      animateCounter(activeCount);
    }
  } catch (err) {
    console.warn('Failed to fetch stats:', err);

    // Fallback: query Supabase directly (if client available)
    if (supabaseClient) {
      try {
        const { data, error } = await supabaseClient
          .from('stats')
          .select('active_count, total_count')
          .eq('id', 1)
          .single();

        if (!error && data) {
          headerActiveCount.textContent = formatNumber(data.total_count || data.active_count);
          animateCounter(data.active_count);
        }
      } catch (e) {
        console.warn('Supabase fallback also failed:', e);
      }
    }
  }
}

// ─── Realtime Subscription ──────────────────────────────────
function setupRealtimeSubscription() {
  if (!supabaseClient) {
    console.log('Supabase client not available, skipping realtime');
    return;
  }
  const channel = supabaseClient
    .channel('stats-realtime')
    .on(
      'postgres_changes',
      {
        event: 'UPDATE',
        schema: 'public',
        table: 'stats',
        filter: 'id=eq.1',
      },
      (payload) => {
        const newActive = payload.new.active_count;
        const newTotal = payload.new.total_count;
        
        if (newTotal !== undefined) {
          headerActiveCount.textContent = formatNumber(newTotal);
        }
        
        if (newActive !== undefined && newActive !== targetCount) {
          animateCounter(newActive);
        }
      }
    )
    .subscribe((status) => {
      if (status === 'SUBSCRIBED') {
        console.log('Realtime subscription active');
      }
    });
}

// Poll every 10 seconds for live counter updates
setInterval(fetchStats, 10000);

// ─── Random Button ──────────────────────────────────────────
randomBtn.addEventListener('click', async () => {
  if (randomBtn.classList.contains('loading')) return;

  randomBtn.classList.add('loading');
  btnText.textContent = 'Finding a website...';

  try {
    const response = await fetch(`${API_BASE}/random`);

    if (response.ok) {
      const data = await response.json();
      if (data.url) {
        btnText.textContent = 'Redirecting...';

        // Use anchor element for reliable new-tab behavior inside iframes
        setTimeout(() => {
          openInNewTab(data.url);
          randomBtn.classList.remove('loading');
          btnText.textContent = 'Take Me Somewhere Random';
        }, 500);
        return;
      }
    }

    // API failed, try direct Supabase query (if client available)
    if (supabaseClient) {
      const { data: websites, error } = await supabaseClient
        .rpc('get_random_active_website');

      if (!error && websites && websites.length > 0) {
        btnText.textContent = 'Redirecting...';
        setTimeout(() => {
          openInNewTab(websites[0].url);
          randomBtn.classList.remove('loading');
          btnText.textContent = 'Take Me Somewhere Random';
        }, 500);
        return;
      }
    }

    showToast('No active websites found yet. The system is still indexing.', 'info');
  } catch (err) {
    console.error('Random fetch error:', err);
    showToast('Failed to get a random website. Please try again.', 'error');
  }

  randomBtn.classList.remove('loading');
  btnText.textContent = 'Take Me Somewhere Random';
});

// ─── Search ─────────────────────────────────────────────────
searchInput.addEventListener('input', (e) => {
  const query = e.target.value.trim();

  clearTimeout(searchDebounceTimer);

  if (query.length < 2) {
    searchResults.innerHTML = '';
    return;
  }

  searchDebounceTimer = setTimeout(() => performSearch(query), 300);
});

async function performSearch(query) {
  try {
    const response = await fetch(
      `${API_BASE}/search?q=${encodeURIComponent(query)}&limit=15`
    );

    if (response.ok) {
      const results = await response.json();
      renderSearchResults(results);
      return;
    }

    // Fallback to direct Supabase (if client available)
    if (supabaseClient) {
      const { data, error } = await supabaseClient
        .from('websites')
        .select('url, domain, is_active')
        .or(`url.ilike.%${query}%,domain.ilike.%${query}%`)
        .eq('is_active', true)
        .limit(15);

      if (!error && data) {
        renderSearchResults(data);
      }
    }
  } catch (err) {
    console.error('Search error:', err);
  }
}

function renderSearchResults(results) {
  if (!results || results.length === 0) {
    searchResults.innerHTML = `
      <div class="search-empty">
        No matching websites found. Try a different search term.
      </div>
    `;
    return;
  }

  searchResults.innerHTML = results
    .map(
      (r) => `
        <a href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer"
           class="search-result-item">
          <div>
            <div class="result-url">${escapeHtml(r.url)}</div>
            <div class="result-domain">${escapeHtml(r.domain)}</div>
          </div>
          <span class="result-arrow">→</span>
        </a>
      `
    )
    .join('');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ─── Submit Form ────────────────────────────────────────────
submitForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const url = submitInput.value.trim();
  if (!url) return;

  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting...';
  submitFeedback.className = 'submit-feedback';
  submitFeedback.style.display = 'none';

  try {
    const response = await fetch(`${API_BASE}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });

    const data = await response.json();

    if (response.ok) {
      submitFeedback.className = 'submit-feedback success';
      submitFeedback.textContent = data.message || 'URL submitted successfully!';
      submitInput.value = '';
    } else {
      submitFeedback.className = 'submit-feedback error';
      submitFeedback.textContent =
        data.detail || 'Failed to submit URL. Please check the format.';
    }
  } catch (err) {
    submitFeedback.className = 'submit-feedback error';
    submitFeedback.textContent = 'Network error. Please try again.';
  }

  submitBtn.disabled = false;
  submitBtn.textContent = 'Submit URL';
});

// ─── Initialize ─────────────────────────────────────────────
async function initApp() {
  // Try to fetch Supabase config from backend
  try {
    const resp = await fetch(`${API_BASE}/config`);
    if (resp.ok) {
      const config = await resp.json();
      if (config.supabase_url && config.supabase_key) {
        supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_key);
        console.log('Supabase client initialized from backend config');
      }
    }
  } catch (e) {
    console.warn('Could not fetch config, running API-only mode:', e);
  }

  fetchStats();
  setupRealtimeSubscription();
}

document.addEventListener('DOMContentLoaded', initApp);
