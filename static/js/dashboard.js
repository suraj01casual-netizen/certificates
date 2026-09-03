/**
 * Dashboard JavaScript - Responsive Navigation & Interactivity
 * Pure Vanilla JavaScript - No dependencies
 */

// ============================================================================
// 1. INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', function () {
  initializeSidebar();
  initializeUserMenu();
  initializeNavigation();
  setupResponsiveListeners();
});

// ============================================================================
// 2. SIDEBAR FUNCTIONALITY
// ============================================================================

function initializeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  const menuToggle = document.getElementById('menuToggle');
  const sidebarClose = document.getElementById('sidebarClose');
  const navLinks = document.querySelectorAll('.sidebar .nav-link');

  // Menu toggle (hamburger)
  if (menuToggle) {
    menuToggle.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleSidebar();
    });
  }

  // Close button
  if (sidebarClose) {
    sidebarClose.addEventListener('click', function (e) {
      e.stopPropagation();
      closeSidebar();
    });
  }

  // Overlay click
  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', closeSidebar);
  }

  // Navigation links
  navLinks.forEach((link) => {
    link.addEventListener('click', function () {
      // Remove active from all sidebar nav items
      document.querySelectorAll('#sidebar .nav-item').forEach((item) => {
        item.classList.remove('active');
      });

      // Add active exclusively to the clicked nav item
      const parentItem = this.closest('.nav-item');
      if (parentItem) {
        parentItem.classList.add('active');
      }

      // Close sidebar on mobile
      if (window.innerWidth < 768) {
        closeSidebar();
      }
    });
  });
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const menuToggle = document.getElementById('menuToggle');

  sidebar.classList.toggle('open');
  overlay.classList.toggle('active');
  menuToggle.classList.toggle('active');

  // Prevent body scroll when sidebar is open
  if (sidebar.classList.contains('open')) {
    document.body.style.overflow = 'hidden';
  } else {
    document.body.style.overflow = '';
  }
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const menuToggle = document.getElementById('menuToggle');

  sidebar.classList.remove('open');
  overlay.classList.remove('active');
  menuToggle.classList.remove('active');
  document.body.style.overflow = '';
}

// ============================================================================
// 3. USER MENU FUNCTIONALITY
// ============================================================================

function initializeUserMenu() {
  const userMenuToggle = document.getElementById('userMenuToggle');
  const userMenu = document.getElementById('userMenu');

  if (!userMenuToggle || !userMenu) return;

  // Toggle menu
  userMenuToggle.addEventListener('click', function (e) {
    e.stopPropagation();
    userMenu.classList.toggle('active');
  });

  // Close menu when clicking outside
  document.addEventListener('click', function (e) {
    if (!userMenu.contains(e.target) && !userMenuToggle.contains(e.target)) {
      userMenu.classList.remove('active');
    }
  });

  // Close menu when clicking on a link
  const menuItems = userMenu.querySelectorAll('a');
  menuItems.forEach((item) => {
    item.addEventListener('click', function () {
      if (!this.getAttribute('target')) {
        userMenu.classList.remove('active');
      }
    });
  });

  // Close menu on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      userMenu.classList.remove('active');
    }
  });
}

// ============================================================================
// 4. NAVIGATION HELPERS
// ============================================================================

function initializeNavigation() {
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  const currentPath = window.location.pathname;
  const navItems = sidebar.querySelectorAll('.nav-item');
  const navLinks = sidebar.querySelectorAll('.nav-link');

  // If server-side Django template already marked exactly one .active item, keep it!
  const serverActiveItems = sidebar.querySelectorAll('.nav-item.active');
  if (serverActiveItems.length === 1) {
    return;
  }

  // Otherwise, determine the single best-matching nav link using highest specificity
  let bestMatchItem = null;
  let bestMatchScore = -1;

  navLinks.forEach((link) => {
    const href = link.getAttribute('href');
    if (!href || href === '#' || href.startsWith('javascript:')) return;

    // Normalise pathname without query parameters or hash
    const linkPath = href.split('?')[0].split('#')[0];
    const navItem = link.closest('.nav-item');
    if (!navItem) return;

    let score = -1;

    if (currentPath === linkPath) {
      // Exact match gets highest priority
      score = 1000 + linkPath.length;
    } else if (linkPath !== '/' && linkPath !== '/dashboard/' && currentPath.startsWith(linkPath)) {
      // Subpath match (e.g. /dashboard/certificates/create/ matching /dashboard/certificates/)
      score = 500 + linkPath.length;
    } else if (currentPath === '/dashboard/' && linkPath === '/dashboard/') {
      score = 100;
    }

    if (score > bestMatchScore) {
      bestMatchScore = score;
      bestMatchItem = navItem;
    }
  });

  // Ensure ONLY the single best match has the .active class
  navItems.forEach((item) => {
    if (bestMatchItem && item === bestMatchItem) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });
}

// ============================================================================
// 5. RESPONSIVE LISTENER
// ============================================================================

function setupResponsiveListeners() {
  // Close sidebar when resizing to desktop view
  window.addEventListener('resize', debounce(function () {
    if (window.innerWidth >= 768) {
      closeSidebar();
    }
  }, 250));

  // Handle orientation changes on mobile
  window.addEventListener('orientationchange', function () {
    closeSidebar();
  });
}

// ============================================================================
// 6. UTILITY FUNCTIONS
// ============================================================================

/**
 * Debounce function to prevent rapid event firing
 */
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Throttle function for scroll events
 */
function throttle(func, limit) {
  let inThrottle;
  return function (...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/**
 * Get cookie value by name
 */
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + '=') {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * Format date to readable string
 */
function formatDate(dateString) {
  const date = new Date(dateString);
  const options = { year: 'numeric', month: 'short', day: 'numeric' };
  return date.toLocaleDateString('en-US', options);
}

/**
 * Format time to readable string
 */
function formatTime(dateString) {
  const date = new Date(dateString);
  const options = { hour: '2-digit', minute: '2-digit' };
  return date.toLocaleTimeString('en-US', options);
}

/**
 * Add event delegation for dynamic elements
 */
function addDelegatedListener(selector, eventType, callback) {
  document.addEventListener(eventType, function (e) {
    const target = e.target.closest(selector);
    if (target) {
      callback.call(target, e);
    }
  });
}

/**
 * Show notification/toast message
 */
function showNotification(message, type = 'info', duration = 3000) {
  const notification = document.createElement('div');
  notification.className = `notification notification-${type}`;
  notification.textContent = message;
  notification.style.cssText = `
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    padding: 1rem 1.5rem;
    background-color: ${
      type === 'success'
        ? '#10b981'
        : type === 'error'
          ? '#ef4444'
          : '#3b82f6'
    };
    color: white;
    border-radius: 0.5rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    font-size: 0.9rem;
    z-index: 1100;
    animation: slideInUp 0.3s ease-out;
  `;

  document.body.appendChild(notification);

  // Auto remove after duration
  if (duration > 0) {
    setTimeout(() => {
      notification.style.animation = 'slideOutDown 0.3s ease-out';
      setTimeout(() => notification.remove(), 300);
    }, duration);
  }

  return notification;
}

/**
 * Close all open menus and modals
 */
function closeAllModals() {
  const userMenu = document.getElementById('userMenu');
  if (userMenu) {
    userMenu.classList.remove('active');
  }
  closeSidebar();
}

// ============================================================================
// 7. ACCESSIBILITY IMPROVEMENTS
// ============================================================================

/**
 * Trap focus within modal/menu for accessibility
 */
function trapFocus(element, onClose) {
  const focusableElements = element.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );

  if (focusableElements.length === 0) return;

  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];

  element.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && onClose) {
      e.preventDefault();
      onClose();
    }

    if (e.key === 'Tab') {
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    }
  });

  // Focus first element
  firstElement.focus();
}

// ============================================================================
// 8. KEYBOARD SHORTCUTS
// ============================================================================

document.addEventListener('keydown', function (e) {
  // Ctrl/Cmd + K to focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
      searchInput.focus();
    }
  }

  // Ctrl/Cmd + B to toggle sidebar
  if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
    e.preventDefault();
    if (window.innerWidth < 768) {
      toggleSidebar();
    }
  }
});

// ============================================================================
// 9. PLACEHOLDER ANIMATION
// ============================================================================

/**
 * Add pulse animation to empty states
 */
function addPulseAnimation() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes pulse {
      0%, 100% {
        opacity: 1;
      }
      50% {
        opacity: 0.5;
      }
    }

    @keyframes slideInUp {
      from {
        opacity: 0;
        transform: translateY(1rem);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @keyframes slideOutDown {
      from {
        opacity: 1;
        transform: translateY(0);
      }
      to {
        opacity: 0;
        transform: translateY(1rem);
      }
    }

    .stat-empty-state,
    .activity-empty-state {
      animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
  `;
  document.head.appendChild(style);
}

// Initialize animations
addPulseAnimation();

// ============================================================================
// 10. EXPORT FOR TESTING (Optional)
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    toggleSidebar,
    closeSidebar,
    showNotification,
    getCookie,
    formatDate,
    formatTime,
    closeAllModals,
  };
}
