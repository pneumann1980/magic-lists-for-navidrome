// Global state for artist selection
let selectedArtistId = null;
let selectedGenre = null;
let allArtists = [];
let allGenres = [];

// Multi-Artist Radio state
let marSelectedArtists = []; // array of {id, name}

// Multi-Genre Mix state
let mgmSelectedGenres = []; // array of genre name strings

// Decade Discovery state
let ddSelectedDecades = []; // array of decade strings

// Sonic Journey state
let sjStartArtistId = null;
let sjEndArtistId = null;

// Genre Archaeology state
let gaSelectedGenre = null;
let currentToast = null;

// Global state for library selection
let selectedLibraryIds = [];
let allLibraries = [];


// Helper function to format dates in friendly format (e.g., "5 Oct 2025 10:12am")
function formatFriendlyDate(dateString) {
    if (!dateString) return 'Never';
    
    const date = new Date(dateString);
    const day = date.getDate();
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[date.getMonth()];
    const year = date.getFullYear();
    
    let hours = date.getHours();
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'pm' : 'am';
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12
    
    return `${day} ${month} ${year} ${hours}:${minutes}${ampm}`;
}

// Toast utility functions
function showToast(type, message, duration = 5000) {
    // Remove any existing toast
    if (currentToast) {
        hideToast(currentToast);
    }

    const container = document.getElementById('toast-container');
    const toastId = 'toast-' + Date.now();

    let bgClass, textClass, borderClass, icon;

    if (type === 'success') {
        bgClass = 'bg-green-50 border-green-200';
        textClass = 'text-green-800';
        borderClass = 'border';
        icon = '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>';
    } else if (type === 'loading') {
        bgClass = 'bg-blue-50 border-blue-200';
        textClass = 'text-blue-800';
        borderClass = 'border';
        icon = '<svg class="size-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
    } else {
        bgClass = 'bg-red-50 border-red-200';
        textClass = 'text-red-800';
        borderClass = 'border';
        icon = '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';
    }

    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `${bgClass} ${borderClass} ${textClass} rounded-lg shadow-lg p-4 pointer-events-auto transition-all duration-300 transform translate-x-0 opacity-100`;
    toast.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="flex-shrink-0">
                ${icon}
            </div>
            <div class="flex-grow">
                <p class="text-sm font-medium">${message}</p>
            </div>
            ${type !== 'loading' ? `
            <button type="button" class="flex-shrink-0 inline-flex items-center justify-center size-5 rounded-lg text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-400" onclick="hideToast('${toastId}')">
                <span class="sr-only">Close</span>
                <svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
            ` : ''}
        </div>
    `;

    container.appendChild(toast);
    currentToast = toastId;

    // Auto-dismiss (except for loading toasts)
    if (type !== 'loading' && duration > 0) {
        setTimeout(() => hideToast(toastId), duration);
    }

    return toastId;
}

function hideToast(toastId) {
    const toast = document.getElementById(toastId);
    if (toast) {
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            if (currentToast === toastId) {
                currentToast = null;
            }
        }, 300);
    }
}

// Mobile menu toggle functionality
const mobileMenuBtn = document.getElementById('hs-navbar-alignment-collapse');
const mobileSidebar = document.getElementById('mobileSidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const closeMobileSidebarBtn = document.getElementById('closeMobileSidebar');

mobileMenuBtn.addEventListener('click', function() {
    mobileSidebar.classList.toggle('-translate-x-full');
    sidebarOverlay.classList.toggle('hidden');
});

// Close sidebar when clicking on close button
closeMobileSidebarBtn.addEventListener('click', function() {
    mobileSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
});

// Close sidebar when clicking on overlay
sidebarOverlay.addEventListener('click', function() {
    mobileSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function(event) {
    if (window.innerWidth < 768 && 
        !mobileSidebar.contains(event.target) && 
        !mobileMenuBtn.contains(event.target) &&
        !mobileSidebar.classList.contains('-translate-x-full')) {
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
});

// Handle window resize to ensure proper state
window.addEventListener('resize', function() {
    if (window.innerWidth >= 768) {
        mobileSidebar.classList.add('-translate-x-full'); // Hide mobile sidebar on large screens
        sidebarOverlay.classList.add('hidden'); // Hide overlay on large screens
    } else {
        // On mobile, ensure sidebar is hidden when switching from desktop view
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
});

// Sidebar navigation active state management
function setActiveMenuItem(page) {
    // Remove active state from all links in desktop sidebar
    const desktopLinks = document.querySelectorAll('#desktopSidebar [data-page]');
    desktopLinks.forEach(link => {
        link.classList.remove('bg-gray-200');
        link.classList.add('bg-gray-100');
    });
    
    // Remove active state from all links in mobile sidebar
    const mobileLinks = document.querySelectorAll('#mobileSidebar [data-page]');
    mobileLinks.forEach(link => {
        link.classList.remove('bg-gray-200');
        link.classList.add('bg-white');
    });
    
    // Add active state to clicked desktop sidebar links
    const activeDesktopLinks = document.querySelectorAll(`#desktopSidebar [data-page="${page}"]`);
    activeDesktopLinks.forEach(link => {
        link.classList.add('bg-gray-200');
        link.classList.remove('bg-gray-100');
    });
    
    // Add active state to clicked mobile sidebar links
    const activeMobileLinks = document.querySelectorAll(`#mobileSidebar [data-page="${page}"]`);
    activeMobileLinks.forEach(link => {
        link.classList.add('bg-gray-200');
        link.classList.remove('bg-white');
    });
}

// Navigation functionality
function showContent(contentId) {
    // Hide all content sections
    const contentSections = ['welcome-content', 'this-is-content', 'rediscover-content', 'genre-mix-content', 'manage-playlists-content', 'system-check-content', 'terms-content', 'multi-artist-radio-content', 'multi-genre-mix-content', 'decade-discovery-content', 'sonic-journey-content', 'genre-archaeology-content'];
    contentSections.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = 'none';
        }
    });

    // Show the selected content
    const targetContent = document.getElementById(contentId);
    if (targetContent) {
        targetContent.style.display = 'block';
    }
}

// Add click handlers to all navigation links
document.addEventListener('click', function(event) {
    const link = event.target.closest('[data-page]');
    if (link) {
        event.preventDefault();
        const page = link.getAttribute('data-page');
        
        // Use the shared navigation handler
        handlePageNavigation(page);
        
        // Update URL based on page (only for click navigation, not popstate)
        updateURL(page);
        
        // Close mobile sidebar if clicked
        if (window.innerWidth < 768) {
            mobileSidebar.classList.add('-translate-x-full');
            sidebarOverlay.classList.add('hidden');
        }
    }
});

// AI model information cache
let aiModelInfo = null;

// Get AI model information for analytics
async function getAIModelInfo() {
    if (aiModelInfo) {
        return aiModelInfo;
    }
    
    try {
        const response = await fetch('/api/ai-model-info');
        if (response.ok) {
            aiModelInfo = await response.json();
            return aiModelInfo;
        }
    } catch (error) {
        console.error('Error fetching AI model info:', error);
    }
    
    // Fallback
    return {
        provider: 'unknown',
        model: 'unknown',
        has_api_key: false
    };
}

// Post-launch library size tracking
async function trackLibrarySize() {
    try {
        const response = await fetch('/api/track-library-size', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();

            if (data.tracked && typeof window.rybbit !== 'undefined') {
                // Track library size event with Rybbit
                window.rybbit.event('Library Size Tracked', {
                    songCount: data.song_count,
                    userId: data.user_id
                });
                console.log('📊 Library size tracked for analytics');
            }
        }
    } catch (error) {
        console.error('❌ Error tracking library size:', error);
    }
}

async function checkDatabaseConnectivity() {
    const alertDiv = document.getElementById('database-error-alert');

    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            // Database is accessible, hide alert
            alertDiv.classList.add('hidden');
        } else {
            // Database error, show alert
            alertDiv.classList.remove('hidden');
        }
    } catch (error) {
        // Network/database error, show alert
        alertDiv.classList.remove('hidden');
        console.error('Database connectivity check failed:', error);
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Preline components
    if (window.HSStaticMethods) {
        window.HSStaticMethods.autoInit();
        console.log('Preline initialized');
    } else {
        console.error('Preline not loaded');
    }
    
    // Setup artist selection change handler
    const artistSelect = document.getElementById('artist-search-select');
    if (artistSelect) {
        artistSelect.addEventListener('change', handleArtistSelection);
        // Add validation on click - highlight library selector if no libraries selected
        artistSelect.addEventListener('click', function() {
            if (selectedLibraryIds.length === 0) {
                // Apply validation styling to library selectors
                const libraryMulti = document.getElementById('library-multi');
                const mobileLibraryMulti = document.getElementById('mobile-library-multi');
                if (libraryMulti) {
                    libraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
                    setTimeout(() => libraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
                }
                if (mobileLibraryMulti) {
                    mobileLibraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
                    setTimeout(() => mobileLibraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
                }
                showToast('warning', 'Please select a music library first.');
            }
        });
    }
    
    // Load libraries on page load
    loadLibraries();

    // Load playlist count on page load
    updatePlaylistCount();

    // Handle initial page routing (with small delay to ensure DOM is ready)
    setTimeout(() => {
        const currentPage = getPageFromURL(window.location.pathname);
        handlePageNavigation(currentPage);
    }, 100);

    // Track library size post-launch (with delay to not interfere with app loading)
    setTimeout(trackLibrarySize, 2000);

    // Check database connectivity
    checkDatabaseConnectivity();
});

// Load artists and populate the select (from original working code)
async function loadArtists() {
    try {
        let url = '/api/artists';
        if (selectedLibraryIds.length > 0) {
            const libraryIdsParam = selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/artists?${libraryIdsParam}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch artists');
        }
        allArtists = await response.json();

        // Clear any previous selection
        selectedArtistId = null;

        // Populate the select dropdown
        const artistSelect = document.getElementById('artist-search-select');
        if (artistSelect) {
            // Clear existing options except the first one
            while (artistSelect.options.length > 1) {
                artistSelect.remove(1);
            }

            // Add artist options
            allArtists.forEach(artist => {
                const option = document.createElement('option');
                option.value = artist.id;
                option.textContent = artist.name;
                artistSelect.appendChild(option);
            });

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                const selectInstance = window.HSSelect.getInstance(artistSelect);
                if (selectInstance) {
                    selectInstance.destroy();
                }
                window.HSSelect.autoInit();
            }
        }
    } catch (error) {
        console.error('Error loading artists:', error);
        showToast('error', 'Failed to load artists from your library');
    }
}

async function loadGenres() {
    try {
        let url = '/api/genres';
        if (selectedLibraryIds.length > 0) {
            const libraryIdsParam = selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/genres?${libraryIdsParam}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch genres');
        }
        allGenres = await response.json();

        // Get the genre select element
        const genreSelect = document.getElementById('genre-select');

        // Update the placeholder text to show genre count
        if (genreSelect && window.HSSelect) {
            const selectInstance = window.HSSelect.getInstance(genreSelect);
            if (selectInstance) {
                selectInstance.destroy();
            }

            // Update the data-hs-select attribute with new placeholder
            const newPlaceholder = `Select from ${allGenres.length} genres...`;
            genreSelect.setAttribute('data-hs-select', JSON.stringify({
                "placeholder": newPlaceholder,
                "toggleTag": "<button type=\"button\"></button>",
                "toggleClasses": "hs-select-disabled:pointer-events-none hs-select-disabled:opacity-50 relative py-3 px-4 pe-9 flex text-nowrap w-full cursor-pointer bg-white border border-gray-200 rounded-lg text-start text-sm focus:border-blue-500 focus:ring-blue-500 before:absolute before:inset-0 before:z-[1]",
                "dropdownClasses": "hs-select-dropdown mt-2 z-50 w-full max-h-72 p-1 space-y-0.5 bg-white border border-gray-200 rounded-lg overflow-hidden overflow-y-auto [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-gray-100 [&::-webkit-scrollbar-thumb]:bg-gray-300",
                "optionClasses": "py-2 px-4 w-full text-sm text-gray-800 cursor-pointer hover:bg-gray-100 rounded-lg focus:outline-none focus:bg-gray-100",
                "optionTemplate": "<div class=\"flex justify-between items-center w-full\"><span data-title></span><span class=\"hidden hs-selected:block\"><svg class=\"flex-shrink-0 size-3.5 text-blue-600\" xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><polyline points=\"20 6 9 17 4 12\"/></svg></span></div>",
                "hasSearch": true,
                "searchPlaceholder": "Search...",
                "searchClasses": "block w-full text-sm border-gray-200 rounded-lg focus:border-blue-500 focus:ring-blue-500 before:absolute before:inset-0 before:z-[1] py-2 px-3",
                "searchWrapperClasses": "bg-white p-2 -mx-1 sticky top-0"
            }));
        }

        // Clear any previous selection
        selectedGenre = null;

        // Populate the select dropdown
        if (genreSelect) {
            // Clear existing options except the first one
            while (genreSelect.options.length > 1) {
                genreSelect.remove(1);
            }

            // Add genre options
            allGenres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre.name;
                option.textContent = `${genre.name} (${genre.songCount})`;
                genreSelect.appendChild(option);
            });

            // Setup genre selection change handler
            genreSelect.addEventListener('change', handleGenreSelection);

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                window.HSSelect.autoInit();
            }
        }
    } catch (error) {
        console.error('Error loading genres:', error);
        showToast('error', 'Failed to load genres from your library');
    }
}

// Handle genre selection change
function handleGenreSelection(e) {
    selectedGenre = e.target.value;
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (selectedGenre) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// Load libraries and populate the multi-select interface
async function loadLibraries() {
    try {
        console.log('📚 Loading libraries from API...');
        console.log(`📚 Current localStorage:`, localStorage.getItem('selectedLibraryIds'));
        const response = await fetch('/api/music-folders');
        if (!response.ok) {
            throw new Error(`Failed to fetch libraries: ${response.status} ${response.statusText}`);
        }
        allLibraries = await response.json();
        console.log(`📚 Loaded ${allLibraries.length} libraries:`, allLibraries);

        // Clear any previous selection
        selectedLibraryIds = [];

        // Get UI elements
        const desktopLoading = document.getElementById('library-loading');
        const desktopSingle = document.getElementById('library-single');
        const desktopSingleName = document.getElementById('library-single-name');
        const desktopMulti = document.getElementById('library-multi');
        const desktopMultiText = document.getElementById('library-multi-text');
        const desktopCheckboxes = document.getElementById('library-checkboxes');

        const mobileLoading = document.getElementById('mobile-library-loading');
        const mobileSingle = document.getElementById('mobile-library-single');
        const mobileSingleName = document.getElementById('mobile-library-single-name');
        const mobileMulti = document.getElementById('mobile-library-multi');
        const mobileMultiText = document.getElementById('mobile-library-multi-text');
        const mobileCheckboxes = document.getElementById('mobile-library-checkboxes');

        // Hide loading states
        if (desktopLoading) desktopLoading.classList.add('hidden');
        if (mobileLoading) mobileLoading.classList.add('hidden');

        // Hide all states initially
        if (desktopSingle) desktopSingle.classList.add('hidden');
        if (mobileSingle) mobileSingle.classList.add('hidden');
        if (desktopMulti) desktopMulti.classList.add('hidden');
        if (mobileMulti) mobileMulti.classList.add('hidden');

        if (allLibraries.length === 1) {
            // Single library - show read-only display (AC1)
            const library = allLibraries[0];
            selectedLibraryIds = [library.id];

            if (desktopSingle && desktopSingleName) {
                desktopSingleName.textContent = library.name;
                desktopSingle.classList.remove('hidden');
            }
            if (mobileSingle && mobileSingleName) {
                mobileSingleName.textContent = library.name;
                mobileSingle.classList.remove('hidden');
            }

            console.log(`📚 Single library detected: ${library.name} (ID: ${library.id}) - showing readonly display`);

            // Save to localStorage
            localStorage.setItem('selectedLibraryIds', JSON.stringify(selectedLibraryIds));
            console.log(`📚 Saved to localStorage:`, selectedLibraryIds);

        } else {
            // Multiple libraries - show multi-select interface (AC2)
            console.log(`📚 Multiple libraries detected: ${allLibraries.length} libraries - showing multi-select`);

            // Load saved library selections from localStorage
            const savedLibraryIds = localStorage.getItem('selectedLibraryIds');
            if (savedLibraryIds) {
                try {
                    const parsedIds = JSON.parse(savedLibraryIds);
                    // Filter to only include libraries that still exist
                    selectedLibraryIds = parsedIds.filter(id => allLibraries.some(lib => lib.id === id));
                    console.log(`📚 Loaded saved library selections:`, selectedLibraryIds);
                } catch (e) {
                    console.warn('📚 Invalid saved library IDs, starting fresh');
                    selectedLibraryIds = [];
                }
            } else {
                console.log('📚 No saved library selections found');
                selectedLibraryIds = [];
            }

            // Create checkboxes for desktop
            if (desktopCheckboxes) {
                desktopCheckboxes.innerHTML = '';
                allLibraries.forEach(library => {
                    const checkboxDiv = document.createElement('div');
                    checkboxDiv.className = 'flex items-center px-3 py-2 hover:bg-gray-50 rounded';
                    checkboxDiv.innerHTML = `
                        <input type="checkbox"
                               id="desktop-lib-${library.id}"
                               value="${library.id}"
                               class="shrink-0 mt-0.5 border-gray-200 rounded text-blue-600 focus:ring-blue-500"
                               ${selectedLibraryIds.includes(library.id) ? 'checked' : ''}>
                        <label for="desktop-lib-${library.id}" class="ml-2 text-sm text-gray-800 cursor-pointer">
                            ${library.name}
                        </label>
                    `;
                    desktopCheckboxes.appendChild(checkboxDiv);
                });
            }

            // Create checkboxes for mobile
            if (mobileCheckboxes) {
                mobileCheckboxes.innerHTML = '';
                allLibraries.forEach(library => {
                    const checkboxDiv = document.createElement('div');
                    checkboxDiv.className = 'flex items-center px-3 py-2 hover:bg-gray-50 rounded';
                    checkboxDiv.innerHTML = `
                        <input type="checkbox"
                               id="mobile-lib-${library.id}"
                               value="${library.id}"
                               class="shrink-0 mt-0.5 border-gray-200 rounded text-blue-600 focus:ring-blue-500"
                               ${selectedLibraryIds.includes(library.id) ? 'checked' : ''}>
                        <label for="mobile-lib-${library.id}" class="ml-2 text-sm text-gray-800 cursor-pointer">
                            ${library.name}
                        </label>
                    `;
                    mobileCheckboxes.appendChild(checkboxDiv);
                });
            }

            // Update display text
            updateLibraryDisplayText();

            // Show multi-select interfaces
            if (desktopMulti) desktopMulti.classList.remove('hidden');
            if (mobileMulti) mobileMulti.classList.remove('hidden');

            // Add event listeners for dropdown toggles
            const desktopToggle = document.getElementById('library-multi-toggle');
            const desktopDropdown = document.getElementById('library-multi-dropdown');
            const mobileToggle = document.getElementById('mobile-library-multi-toggle');
            const mobileDropdown = document.getElementById('mobile-library-multi-dropdown');

            if (desktopToggle && desktopDropdown) {
                desktopToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    desktopDropdown.classList.toggle('hidden');
                });
            }
            if (mobileToggle && mobileDropdown) {
                mobileToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    mobileDropdown.classList.toggle('hidden');
                });
            }

            // Add event listeners for checkboxes
            allLibraries.forEach(library => {
                const desktopCheckbox = document.getElementById(`desktop-lib-${library.id}`);
                const mobileCheckbox = document.getElementById(`mobile-lib-${library.id}`);

                if (desktopCheckbox) {
                    desktopCheckbox.addEventListener('change', handleLibraryCheckboxChange);
                }
                if (mobileCheckbox) {
                    mobileCheckbox.addEventListener('change', handleLibraryCheckboxChange);
                }
            });

            // Close dropdowns when clicking outside
            document.addEventListener('click', (e) => {
                if (desktopDropdown && !desktopMulti.contains(e.target)) {
                    desktopDropdown.classList.add('hidden');
                }
                if (mobileDropdown && !mobileMulti.contains(e.target)) {
                    mobileDropdown.classList.add('hidden');
                }
            });
        }

    } catch (error) {
        console.error('Error loading libraries:', error);
        showToast('error', 'Failed to load music libraries');

        // Hide loading and show error state
        const desktopLoading = document.getElementById('library-loading');
        const mobileLoading = document.getElementById('mobile-library-loading');
        const desktopSingle = document.getElementById('library-single');
        const mobileSingle = document.getElementById('mobile-library-single');
        const desktopMulti = document.getElementById('library-multi');
        const mobileMulti = document.getElementById('mobile-library-multi');

        // Hide all states
        if (desktopLoading) desktopLoading.classList.add('hidden');
        if (mobileLoading) mobileLoading.classList.add('hidden');
        if (desktopSingle) desktopSingle.classList.add('hidden');
        if (mobileSingle) mobileSingle.classList.add('hidden');
        if (desktopMulti) desktopMulti.classList.add('hidden');
        if (mobileMulti) mobileMulti.classList.add('hidden');
    }
}

// Handle library selection change


// Update the display text for multi-library selector
function updateLibraryDisplayText() {
    const desktopText = document.getElementById('library-multi-text');
    const mobileText = document.getElementById('mobile-library-multi-text');

    if (selectedLibraryIds.length === 0) {
        if (desktopText) desktopText.textContent = 'Select library';
        if (mobileText) mobileText.textContent = 'Select library';
        if (desktopText) desktopText.className = 'text-gray-500 truncate';
        if (mobileText) mobileText.className = 'text-gray-500 truncate';
    } else if (selectedLibraryIds.length === 1) {
        const library = allLibraries.find(lib => lib.id === selectedLibraryIds[0]);
        const libraryName = library ? library.name : '1 library';
        if (desktopText) desktopText.textContent = libraryName;
        if (mobileText) mobileText.textContent = libraryName;
        if (desktopText) desktopText.className = 'text-gray-900 truncate';
        if (mobileText) mobileText.className = 'text-gray-900 truncate';
    } else {
        if (desktopText) desktopText.textContent = `${selectedLibraryIds.length} libraries`;
        if (mobileText) mobileText.textContent = `${selectedLibraryIds.length} libraries`;
        if (desktopText) desktopText.className = 'text-gray-900 truncate';
        if (mobileText) mobileText.className = 'text-gray-900 truncate';
    }
}

// Handle library checkbox changes
function handleLibraryCheckboxChange(e) {
    const libraryId = e.target.value;
    const isChecked = e.target.checked;

    if (isChecked) {
        if (!selectedLibraryIds.includes(libraryId)) {
            selectedLibraryIds.push(libraryId);
        }
    } else {
        selectedLibraryIds = selectedLibraryIds.filter(id => id !== libraryId);
    }

    // Sync checkboxes between desktop and mobile
    const desktopCheckbox = document.getElementById(`desktop-lib-${libraryId}`);
    const mobileCheckbox = document.getElementById(`mobile-lib-${libraryId}`);

    if (desktopCheckbox && desktopCheckbox !== e.target) {
        desktopCheckbox.checked = isChecked;
    }
    if (mobileCheckbox && mobileCheckbox !== e.target) {
        mobileCheckbox.checked = isChecked;
    }

    // Update localStorage
    localStorage.setItem('selectedLibraryIds', JSON.stringify(selectedLibraryIds));

    // Update display text
    updateLibraryDisplayText();

    // Refresh current page content if needed
    const currentPage = getPageFromURL(window.location.pathname);
    if (currentPage === 'this-is-artist') {
        loadArtists();
    } else if (currentPage === 'genre-mix') {
        loadGenres();
    } else if (currentPage === 'multi-artist-radio') {
        loadArtistsForMAR();
    } else if (currentPage === 'multi-genre-mix') {
        loadGenresForMGM();
    } else if (currentPage === 'sonic-journey') {
        loadArtistsForSJ();
    } else if (currentPage === 'genre-archaeology') {
        loadGenresForGA();
    }

    console.log(`📚 Library selection updated:`, selectedLibraryIds);
}

// Check if libraries are selected and show warning if not
function checkLibrarySelection() {
    if (selectedLibraryIds.length === 0) {
        showToast('warning', 'Please select a music library.');
        // Highlight the library selector
        const libraryMulti = document.getElementById('library-multi');
        const mobileLibraryMulti = document.getElementById('mobile-library-multi');
        if (libraryMulti) {
            libraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
            setTimeout(() => libraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
        }
        if (mobileLibraryMulti) {
            mobileLibraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
            setTimeout(() => mobileLibraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
        }
        return false;
    }
    return true;
}

// Handle artist selection change
function handleArtistSelection(e) {
    selectedArtistId = e.target.value;
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (selectedArtistId) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// This Is Artist form submission
document.getElementById('this-is-form').addEventListener('submit', function(e) {
    e.preventDefault();
    createArtistPlaylist();
});

// Genre Mix form submission
document.getElementById('genre-mix-form').addEventListener('submit', function(e) {
    e.preventDefault();
    createGenrePlaylist();
});

async function createArtistPlaylist() {
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (!selectedArtistId) {
        showToast('error', 'Please select an artist first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="artist-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="artist-playlist-length"]:checked').value;

        const response = await fetch('/api/create_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_ids: [selectedArtistId],
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();

        // Track successful artist playlist creation with Rybbit
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('This Is Playlist Created', {
                trackCount: data.songs ? data.songs.length : 0,
                refreshFrequency: refreshFrequency,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider
            });
        }

        // Show success toast
        showToast('success', `Playlist created with ${data.songs ? data.songs.length : 0} tracks`);
        
        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error creating playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

async function createGenrePlaylist() {
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (!selectedGenre) {
        showToast('error', 'Please select a genre first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="genre-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="genre-playlist-length"]:checked').value;

        const response = await fetch('/api/create_genre_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                genre: selectedGenre,
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();

        // Track successful genre playlist creation with Rybbit
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('Genre Mix Playlist Created', {
                trackCount: data.songs ? data.songs.length : 0,
                refreshFrequency: refreshFrequency,
                genre: selectedGenre,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider
            });
        }

        // Show success toast
        showToast('success', `Playlist created with ${data.songs ? data.songs.length : 0} tracks`);

        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error creating playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

// Re-discover Weekly functionality
async function generateRediscoverWeekly() {
    const button = document.getElementById('rediscover-btn');

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Analyzing your listening history...', 0);
    button.disabled = true;

    try {
        // Use v2.0 create endpoint (generates and creates playlist in one step)
        const refreshFrequency = document.querySelector('input[name="rediscover-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="rediscover-playlist-length"]:checked').value;

        const response = await fetch('/api/create-rediscover-playlist-v2', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create Re-Discover playlist');
        }

        const data = await response.json();

        // Track successful Re-Discover playlist creation
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('Re-Discover Playlist Created', {
                trackCount: data.track_count,
                theme: data.theme,
                mode: data.mode,
                refreshFrequency: refreshFrequency,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider,
                isFallback: data.is_fallback || false
            });
        }

        // Show success message
        const fallbackMsg = data.is_fallback ? ' (using fallback strategy)' : '';
        showToast('success', `Re-Discover playlist created! "${data.theme}" theme with ${data.track_count} tracks${fallbackMsg}`);

    } catch (error) {
        showToast('error', error.message);
    } finally {
        button.disabled = false;
    }
}

// Handle version selection changes (removed - always use v2.0)
function handleVersionChange() {
    const button = document.getElementById('rediscover-btn');
    button.textContent = 'Generate Re-Discover Playlist';
}

// Initialize button text
document.addEventListener('DOMContentLoaded', function() {
    // Set initial button text
    handleVersionChange();
});

// Update playlist count in sidebar
async function updatePlaylistCount() {
    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            const playlists = await response.json();
            const count = playlists.length;
            
            // Update both desktop and mobile sidebar text
            const desktopText = document.getElementById('desktop-playlists-text');
            const mobileText = document.getElementById('mobile-playlists-text');
            
            if (count > 0) {
                if (desktopText) desktopText.textContent = `Playlists (${count})`;
                if (mobileText) mobileText.textContent = `Playlists (${count})`;
            } else {
                if (desktopText) desktopText.textContent = 'Playlists';
                if (mobileText) mobileText.textContent = 'Playlists';
            }
        }
    } catch (error) {
        console.error('Error fetching playlist count:', error);
        // Keep default text on error
    }
}

// Manage Playlists functionality
// Format next refresh time in a user-friendly way
function formatNextRefresh(nextRefreshTime) {
    const nextRefresh = new Date(nextRefreshTime);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    const nextRefreshDate = new Date(nextRefresh.getFullYear(), nextRefresh.getMonth(), nextRefresh.getDate());
    
    const timeString = nextRefresh.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit', hour12: true});
    
    if (nextRefreshDate.getTime() === today.getTime()) {
        return `${timeString} today`;
    } else if (nextRefreshDate.getTime() === tomorrow.getTime()) {
        return `${timeString} tomorrow`;
    } else {
        return `${nextRefresh.toLocaleDateString('en-GB')} ${timeString}`;
    }
}

async function loadPlaylists() {
    const loadingDiv = document.getElementById('playlists-loading');
    const containerDiv = document.getElementById('playlists-container');

    loadingDiv.classList.remove('hidden');
    containerDiv.innerHTML = '';

    try {
        const response = await fetch('/api/playlists');
        if (!response.ok) {
            throw new Error('Failed to load playlists');
        }

        let playlists = await response.json();
        
        loadingDiv.classList.add('hidden');
        
        // Filter duplicates by navidrome_playlist_id to address backend JOIN issue
        const seenIds = new Set();
        playlists = playlists.filter(playlist => {
            // Use navidrome_playlist_id as unique identifier
            const id = playlist.navidrome_playlist_id || playlist.id; // fallback to id if no navidrome id
            if (seenIds.has(id)) {
                return false; // duplicate, filter out
            }
            seenIds.add(id);
            return true; // unique, keep
        });
        
        if (playlists.length === 0) {
            containerDiv.innerHTML = `
                <div class="text-center p-8 text-gray-500">
                    <p class="text-lg mb-2">No playlists yet</p>
                    <p class="text-sm">Create your first playlist using the options in the sidebar!</p>
                </div>
            `;
            return;
        }

        renderPlaylists(playlists);

    } catch (error) {
        console.error('Error loading playlists:', error);
        loadingDiv.classList.add('hidden');
        containerDiv.innerHTML = `
            <div class="text-center p-8 text-red-600">
                <p class="text-lg mb-2">Error loading playlists</p>
                <p class="text-sm">${error.message}</p>
            </div>
        `;
    }
}

function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

function renderPlaylists(playlists) {
    const container = document.getElementById('playlists-container');

    container.innerHTML = playlists.map(playlist => {
        const hasSchedule = playlist.refresh_frequency && playlist.refresh_frequency !== 'none';
        const escapedName = playlist.playlist_name.replace(/'/g, "\\'").replace(/"/g, '&quot;');

        return `
            <div class="border border-gray-200 rounded-lg mb-4 overflow-hidden" id="playlist-card-${playlist.id}">
                <div class="flex items-start justify-between p-4">
                    <div class="flex-grow min-w-0">
                        <h3 class="text-lg font-semibold text-gray-900 mb-1">${playlist.playlist_name}</h3>
                        <div class="text-sm text-gray-600 mb-2 space-y-1">
                            <p class="mb-0">
                                ${playlist.track_count || 0} tracks •
                                Refreshes <span id="freq-label-${playlist.id}">${playlist.refresh_frequency || 'manually'}</span> •
                                <span id="next-refresh-label-${playlist.id}">${playlist.next_refresh ? `Next ${formatNextRefresh(playlist.next_refresh)}` : 'No scheduled refresh'}</span>
                            </p>
                            <p class="mb-0">
                                Created ${formatFriendlyDate(playlist.created_at)} •
                                <span id="last-refreshed-label-${playlist.id}">${playlist.last_refreshed ? `Refreshed ${formatFriendlyDate(playlist.last_refreshed)}` : 'Not refreshed yet'}</span>
                            </p>
                        </div>
                        ${playlist.reasoning ? `<p class="text-sm text-gray-600 m-0 mt-2 italic">${truncateText(playlist.reasoning, 140)}</p>` : ''}
                    </div>
                    <div class="flex-none flex flex-col items-end gap-1 ml-4">
                        ${hasSchedule ? `
                        <button
                            id="refresh-btn-${playlist.id}"
                            onclick="refreshPlaylistNow(${playlist.id}, '${escapedName}')"
                            class="text-sm font-medium cursor-pointer border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded px-2 py-1 whitespace-nowrap"
                        >
                            Refresh Now
                        </button>
                        ` : ''}
                        <button
                            onclick="toggleModifyPanel(${playlist.id})"
                            class="text-sm font-medium cursor-pointer border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 rounded px-2 py-1 whitespace-nowrap"
                        >
                            Modify
                        </button>
                        <button
                            onclick="deletePlaylist(${playlist.id}, '${escapedName}')"
                            class="text-sm font-medium cursor-pointer border-none bg-transparent text-red-600 hover:text-red-800 px-2 py-1 whitespace-nowrap"
                        >
                            Delete
                        </button>
                    </div>
                </div>
                <!-- Inline modify panel (hidden by default) -->
                <div id="modify-panel-${playlist.id}" class="hidden border-t border-gray-100 bg-gray-50 px-4 py-3">
                    <p class="text-sm font-medium text-gray-700 mb-2">Refresh frequency</p>
                    <div class="flex flex-wrap items-center gap-2">
                        <select
                            id="freq-select-${playlist.id}"
                            class="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                        >
                            <option value="none" ${(!playlist.refresh_frequency || playlist.refresh_frequency === 'none') ? 'selected' : ''}>No auto-refresh</option>
                            <option value="daily" ${playlist.refresh_frequency === 'daily' ? 'selected' : ''}>Daily</option>
                            <option value="weekly" ${playlist.refresh_frequency === 'weekly' ? 'selected' : ''}>Weekly</option>
                            <option value="monthly" ${playlist.refresh_frequency === 'monthly' ? 'selected' : ''}>Monthly</option>
                        </select>
                        <button
                            onclick="savePlaylistSettings(${playlist.id})"
                            class="text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2 cursor-pointer border-0"
                        >
                            Save
                        </button>
                        <button
                            onclick="toggleModifyPanel(${playlist.id})"
                            class="text-sm text-gray-500 hover:text-gray-700 cursor-pointer border-none bg-transparent px-2 py-2"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function toggleModifyPanel(playlistId) {
    const panel = document.getElementById(`modify-panel-${playlistId}`);
    if (panel) {
        panel.classList.toggle('hidden');
    }
}

async function savePlaylistSettings(playlistId) {
    const select = document.getElementById(`freq-select-${playlistId}`);
    if (!select) return;

    const newFrequency = select.value;

    try {
        const response = await fetch(`/api/playlists/${playlistId}/settings`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_frequency: newFrequency })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || 'Failed to save settings');
        }

        const data = await response.json();

        // Update labels in place without a full reload
        const freqLabel = document.getElementById(`freq-label-${playlistId}`);
        const nextLabel = document.getElementById(`next-refresh-label-${playlistId}`);
        const card = document.getElementById(`playlist-card-${playlistId}`);

        if (freqLabel) freqLabel.textContent = newFrequency === 'none' ? 'manually' : newFrequency;

        if (nextLabel) {
            if (data.next_refresh) {
                nextLabel.textContent = `Next ${formatNextRefresh(data.next_refresh)}`;
            } else {
                nextLabel.textContent = 'No scheduled refresh';
            }
        }

        // Show/hide the Refresh Now button based on new frequency
        const refreshBtn = document.getElementById(`refresh-btn-${playlistId}`);
        const actionsDiv = refreshBtn ? refreshBtn.parentElement : null;
        if (actionsDiv) {
            if (newFrequency !== 'none' && !refreshBtn) {
                // Re-render to show the Refresh Now button (simplest approach)
                loadPlaylists();
                return;
            } else if (newFrequency === 'none' && refreshBtn) {
                refreshBtn.remove();
            }
        }

        // Hide the panel
        toggleModifyPanel(playlistId);
        showToast('success', 'Refresh settings updated successfully');

    } catch (error) {
        console.error('Error saving playlist settings:', error);
        showToast('error', error.message);
    }
}

async function refreshPlaylistNow(playlistId, playlistName) {
    const btn = document.getElementById(`refresh-btn-${playlistId}`);
    const originalText = btn ? btn.textContent : 'Refresh Now';

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Refreshing…';
        btn.classList.add('opacity-60', 'cursor-not-allowed');
    }

    const toastId = showToast('loading', `Refreshing "${playlistName}"… This may take a minute.`, 0);

    try {
        const response = await fetch(`/api/playlists/${playlistId}/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(err.detail || 'Failed to refresh playlist');
        }

        hideToast(toastId);
        showToast('success', `"${playlistName}" has been refreshed successfully!`);

        // Update the "last refreshed" label by reloading playlist list
        loadPlaylists();

    } catch (error) {
        console.error('Error refreshing playlist:', error);
        hideToast(toastId);
        showToast('error', error.message);

        if (btn) {
            btn.disabled = false;
            btn.textContent = originalText;
            btn.classList.remove('opacity-60', 'cursor-not-allowed');
        }
    }
}

async function deletePlaylist(playlistId, playlistName) {
    if (!confirm(`Are you sure you want to delete "${playlistName}"?\n\nThis will permanently remove the playlist from both Magic Lists and your Navidrome library.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/playlists/${playlistId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to delete playlist');
        }

        // Reload the playlists list and update count
        loadPlaylists();
        updatePlaylistCount();

        // Show success toast - note that the backend may only delete locally if Navidrome deletion fails
        showToast('success', 'Playlist deleted from local database (check Navidrome if it still appears there)');

    } catch (error) {
        console.error('Error deleting playlist:', error);
        showToast('error', error.message);
    }
}

// System Check functionality
async function runSystemChecks() {
    const listContainer = document.getElementById('system-checks-list');
    const resultsContainer = document.getElementById('system-check-results');
    const successBanner = document.getElementById('success-banner');
    const errorBanner = document.getElementById('error-banner');
    const updateSettingsBtn = document.getElementById('update-settings-btn');
    const rerunBtn = document.getElementById('rerun-checks-btn');

    // Reset UI
    successBanner.classList.add('hidden');
    errorBanner.classList.add('hidden');
    updateSettingsBtn.classList.add('hidden');
    rerunBtn.disabled = true;
    rerunBtn.innerHTML = `
        <svg class="animate-spin h-4 w-4 text-gray-400 mr-2 inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-gray-400">Running checks...</span>
    `;

    try {
        // Call backend health check endpoint
        const response = await fetch('/api/health-check');
        if (!response.ok) {
            throw new Error('Failed to run system checks');
        }

        const data = await response.json();
        
        // Display check results
        displaySystemChecks(data.checks);
        
        // Show appropriate banner and buttons
        if (data.all_passed) {
            successBanner.classList.remove('hidden');
            
            // Track Rybbit event
            if (typeof window.rybbit !== 'undefined') {
                window.rybbit.event('System Check Completed', {
                    status: 'all_passed',
                    checkCount: data.checks ? data.checks.length : 0
                });
            }
        } else {
            errorBanner.classList.remove('hidden');
            updateSettingsBtn.classList.remove('hidden');
            
            // Track specific failure events with Rybbit
            if (typeof window.rybbit !== 'undefined') {
                const failedChecks = data.checks.filter(check => check.status === 'error');
                
                window.rybbit.event('System Check Completed', {
                    status: 'failed',
                    checkCount: data.checks ? data.checks.length : 0,
                    failedCount: failedChecks.length
                });
                
                // Track specific failure types
                failedChecks.forEach(check => {
                    if (check.name.includes('URL Reachable')) {
                        window.rybbit.event('System Check Failed', { type: 'url_reachable' });
                    } else if (check.name.includes('Authentication')) {
                        window.rybbit.event('System Check Failed', { type: 'authentication' });
                    } else if (check.name.includes('Artists API')) {
                        window.rybbit.event('System Check Failed', { type: 'artists_api' });
                    } else if (check.name.includes('AI Provider')) {
                        window.rybbit.event('System Check Failed', { type: 'ai_provider' });
                    }
                });
            }
        }
        
    } catch (error) {
        console.error('System check error:', error);
        listContainer.innerHTML = `
            <div class="p-4 text-red-600 border border-red-300 rounded-lg bg-red-50">
                <p class="font-medium">Error running system checks</p>
                <p class="text-sm mt-1">${error.message}</p>
            </div>
        `;
        errorBanner.classList.remove('hidden');
    } finally {
        rerunBtn.disabled = false;
        rerunBtn.innerHTML = 'Re-run Checks';
    }
}

function displaySystemChecks(checks) {
    const container = document.getElementById('system-checks-list');
    
    container.innerHTML = checks.map(check => {
        const statusIcon = getStatusIcon(check.status);
        const statusColor = getStatusColor(check.status);
        const hasDetails = check.message || check.suggestion;
        
        return `
            <div class="border border-gray-200 rounded-lg overflow-hidden">
                <div class="p-4 ${hasDetails ? 'cursor-pointer' : ''}" ${hasDetails ? `onclick="toggleCheckDetails('${check.name.replace(/[^a-zA-Z0-9]/g, '')}')"` : ''}>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                ${statusIcon}
                            </div>
                            <div class="ml-3">
                                <h3 class="text-sm font-medium text-gray-900">${check.name}</h3>
                                ${check.status !== 'success' ? `<p class="text-sm ${statusColor}">${getStatusText(check.status)}</p>` : ''}
                            </div>
                        </div>
                        ${hasDetails ? `
                            <div class="flex-shrink-0">
                                <svg class="w-5 h-5 text-gray-400 transform transition-transform rotate-90" id="chevron-${check.name.replace(/[^a-zA-Z0-9]/g, '')}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
                                </svg>
                            </div>
                        ` : ''}
                    </div>
                </div>
                ${hasDetails ? `
                    <div class="hidden px-4 pb-4 pt-4 border-t border-gray-100 bg-gray-50" id="details-${check.name.replace(/[^a-zA-Z0-9]/g, '')}">
                        ${check.message ? `<p class="text-sm text-gray-600 mb-2">${check.message}</p>` : ''}
                        ${check.suggestion ? `<p class="text-sm text-blue-600 font-medium">${check.suggestion}</p>` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function toggleCheckDetails(checkId) {
    const detailsDiv = document.getElementById(`details-${checkId}`);
    const chevron = document.getElementById(`chevron-${checkId}`);
    
    if (detailsDiv.classList.contains('hidden')) {
        detailsDiv.classList.remove('hidden');
        chevron.classList.remove('rotate-90');
        chevron.classList.add('-rotate-90');
    } else {
        detailsDiv.classList.add('hidden');
        chevron.classList.remove('-rotate-90');
        chevron.classList.add('rotate-90');
    }
}

function getStatusIcon(status) {
    switch (status) {
        case 'success':
            return `<svg class="w-5 h-5 text-green-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
            </svg>`;
        case 'warning':
            return `<svg class="w-5 h-5 text-yellow-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>`;
        case 'info':
            return `<svg class="w-5 h-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
            </svg>`;
        case 'error':
            return `<svg class="w-5 h-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
            </svg>`;
        default:
            return `<svg class="w-5 h-5 text-gray-400 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="m12 2v4l4-4h-4z"></path>
            </svg>`;
    }
}

function getStatusColor(status) {
    switch (status) {
        case 'success':
            return 'text-green-600';
        case 'warning':
            return 'text-yellow-600';
        case 'info':
            return 'text-blue-600';
        case 'error':
            return 'text-red-600';
        default:
            return 'text-gray-500';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'success':
            return 'Success';
        case 'warning':
            return 'Warning';
        case 'info':
            return '';
        case 'error':
            return 'Failed';
        default:
            return 'Checking...';
    }
}

// URL management function
function updateURL(page) {
    let url = '/';
    
    // Map pages to URL paths
    switch(page) {
        case 'home':
            url = '/';
            break;
        case 'this-is-artist':
            url = '/this-is';
            break;
        case 're-discover':
            url = '/re-discover';
            break;
        case 'genre-mix':
            url = '/genre-mix';
            break;
        case 'playlists':
            url = '/playlists';
            break;
        case 'system-check':
            url = '/system-check';
            break;
        case 'terms':
            url = '/terms';
            break;
        case 'multi-artist-radio':
            url = '/multi-artist-radio';
            break;
        case 'multi-genre-mix':
            url = '/multi-genre-mix';
            break;
        case 'decade-discovery':
            url = '/decade-discovery';
            break;
        case 'sonic-journey':
            url = '/sonic-journey';
            break;
        case 'genre-archaeology':
            url = '/genre-archaeology';
            break;
        default:
            url = '/';
    }
    
    // Update browser URL without page reload
    if (window.location.pathname !== url) {
        window.history.pushState({ page: page }, '', url);
    }
}

function navigateToHome() {
    // Navigate to home page (this will trigger a redirect to / which checks system status)
    window.location.href = '/';
}

function showSettingsHelp() {
    alert('To update your settings:\n\n1. Edit your .env file with the correct values\n2. Restart the application\n3. Run the system check again\n\nRefer to the SETUP.md file for detailed configuration instructions.');
}

// Auto-run system checks when the system-check page loads
function initSystemCheckPage() {
    runSystemChecks();
}

// URL ROUTING
// Handle browser back/forward navigation
window.addEventListener('popstate', function(event) {
    if (event.state && event.state.page) {
        // Use the stored page state
        handlePageNavigation(event.state.page);
    } else {
        // Determine page from URL
        const page = getPageFromURL(window.location.pathname);
        handlePageNavigation(page);
    }
});

// Get page from URL path
function getPageFromURL(pathname) {
    let page;
    switch(pathname) {
        case '/':
            page = 'home';
            break;
        case '/this-is':
            page = 'this-is-artist';
            break;
        case '/re-discover':
            page = 're-discover';
            break;
        case '/genre-mix':
            page = 'genre-mix';
            break;
        case '/playlists':
            page = 'playlists';
            break;
        case '/system-check':
            page = 'system-check';
            break;
        case '/terms':
            page = 'terms';
            break;
        case '/multi-artist-radio':
            page = 'multi-artist-radio';
            break;
        case '/multi-genre-mix':
            page = 'multi-genre-mix';
            break;
        case '/decade-discovery':
            page = 'decade-discovery';
            break;
        case '/sonic-journey':
            page = 'sonic-journey';
            break;
        case '/genre-archaeology':
            page = 'genre-archaeology';
            break;
        default:
            page = 'home';
            break;
    }
    return page;
}

// Handle page navigation (used by both click and popstate)
function handlePageNavigation(page) {
    // Track page view with Rybbit
    if (typeof window.rybbit !== 'undefined') {
        window.rybbit.pageview();
    }

    // Map page to content
    let contentId;
    if (page === 'home') {
        contentId = 'welcome-content';
    } else if (page === 'this-is-artist') {
        contentId = 'this-is-content';
        // Load artists when navigating to This Is page (only if libraries selected)
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadArtists(), 100);
        }
    } else if (page === 're-discover') {
        contentId = 'rediscover-content';
    } else if (page === 'genre-mix') {
        contentId = 'genre-mix-content';
        // Load genres when navigating to Genre Mix page (only if libraries selected)
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadGenres(), 100);
        }
    } else if (page === 'playlists') {
        contentId = 'manage-playlists-content';
        // Load playlists when navigating to manage page
        setTimeout(() => loadPlaylists(), 100);
    } else if (page === 'system-check') {
        contentId = 'system-check-content';
        // Auto-run system checks when navigating to system check page
        setTimeout(() => runSystemChecks(), 100);
    } else if (page === 'terms') {
        contentId = 'terms-content';
    } else if (page === 'multi-artist-radio') {
        contentId = 'multi-artist-radio-content';
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadArtistsForMAR(), 100);
        }
    } else if (page === 'multi-genre-mix') {
        contentId = 'multi-genre-mix-content';
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadGenresForMGM(), 100);
        }
    } else if (page === 'decade-discovery') {
        contentId = 'decade-discovery-content';
        setTimeout(() => initDecadeChips(), 100);
    } else if (page === 'sonic-journey') {
        contentId = 'sonic-journey-content';
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadArtistsForSJ(), 100);
        }
    } else if (page === 'genre-archaeology') {
        contentId = 'genre-archaeology-content';
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadGenresForGA(), 100);
        }
    }

    setActiveMenuItem(page);
    showContent(contentId);
}




// ============================================================
// MULTI-ARTIST RADIO
// ============================================================

async function loadArtistsForMAR() {
    if (allArtists.length === 0) {
        try {
            const url = selectedLibraryIds.length > 0
                ? `/api/artists?library_ids=${selectedLibraryIds.join(',')}`
                : '/api/artists';
            const response = await fetch(url);
            if (response.ok) allArtists = await response.json();
        } catch (e) { console.error('Failed to load artists for MAR:', e); return; }
    }
    const select = document.getElementById('mar-artist-select');
    if (!select) return;
    while (select.options.length > 1) select.remove(1);
    allArtists.forEach(artist => {
        const opt = document.createElement('option');
        opt.value = artist.id;
        opt.textContent = artist.name;
        select.appendChild(opt);
    });
    select.onchange = function() {
        const artistId = this.value;
        if (!artistId) return;
        if (marSelectedArtists.find(a => a.id === artistId)) { this.value = ''; return; }
        if (marSelectedArtists.length >= 6) { showToast('error', 'Maximum 6 artists allowed'); this.value = ''; return; }
        const artist = allArtists.find(a => a.id === artistId);
        if (!artist) return;
        marSelectedArtists.push({ id: artist.id, name: artist.name });
        renderMARTags();
        this.value = '';
        updateMARSubmitButton();
    };
}

function renderMARTags() {
    const container = document.getElementById('mar-selected-artists');
    const placeholder = document.getElementById('mar-artist-placeholder');
    const countEl = document.getElementById('mar-artist-count');
    if (!container) return;
    container.querySelectorAll('.mar-tag').forEach(t => t.remove());
    if (marSelectedArtists.length === 0) {
        if (placeholder) placeholder.style.display = '';
    } else {
        if (placeholder) placeholder.style.display = 'none';
        marSelectedArtists.forEach(artist => {
            const tag = document.createElement('span');
            tag.className = 'mar-tag inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800';
            tag.innerHTML = `${artist.name} <button type="button" onclick="removeMARartist('${artist.id}')" class="ml-1 hover:text-blue-600 font-bold">&times;</button>`;
            container.appendChild(tag);
        });
    }
    if (countEl) countEl.textContent = marSelectedArtists.length;
}

function removeMARartist(artistId) {
    marSelectedArtists = marSelectedArtists.filter(a => a.id !== artistId);
    renderMARTags();
    updateMARSubmitButton();
}

function updateMARSubmitButton() {
    const btn = document.getElementById('create-mar-playlist-btn');
    if (btn) btn.disabled = marSelectedArtists.length < 2;
}

document.addEventListener('DOMContentLoaded', function() {
    const marForm = document.getElementById('multi-artist-radio-form');
    if (marForm) {
        marForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (!checkLibrarySelection()) return;
            if (marSelectedArtists.length < 2) { showToast('error', 'Please select at least 2 artists'); return; }
            const btn = document.getElementById('create-mar-playlist-btn');
            btn.disabled = true;
            showToast('loading', 'Creating your Artist Radio blend...', 0);
            try {
                const refreshFrequency = document.querySelector('input[name="mar-refresh-frequency"]:checked').value;
                const playlistLength = parseInt(document.querySelector('input[name="mar-playlist-length"]:checked').value);
                const response = await fetch('/api/create-multi-artist-radio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ artist_ids: marSelectedArtists.map(a => a.id), refresh_frequency: refreshFrequency, playlist_length: playlistLength, library_ids: selectedLibraryIds })
                });
                if (!response.ok) { const err = await response.json().catch(() => ({ detail: 'Unknown error' })); throw new Error(err.detail || 'Failed'); }
                const data = await response.json();
                showToast('success', `Artist Radio created with ${data.songs ? data.songs.length : playlistLength} tracks`);
                updatePlaylistCount();
            } catch (error) { showToast('error', error.message); }
            finally { btn.disabled = marSelectedArtists.length < 2; }
        });
    }
});

// ============================================================
// MULTI-GENRE MIX
// ============================================================

async function loadGenresForMGM() {
    if (allGenres.length === 0) {
        try {
            const url = selectedLibraryIds.length > 0
                ? `/api/genres?library_ids=${selectedLibraryIds.join(',')}`
                : '/api/genres';
            const response = await fetch(url);
            if (response.ok) allGenres = await response.json();
        } catch (e) { console.error('Failed to load genres for MGM:', e); return; }
    }
    const container = document.getElementById('mgm-genre-chips');
    const loading = document.getElementById('mgm-genre-loading');
    if (!container) return;
    if (loading) loading.remove();
    container.querySelectorAll('.mgm-chip').forEach(c => c.remove());
    allGenres.forEach(genre => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'mgm-chip px-3 py-1 rounded-full text-sm border border-gray-300 bg-white text-gray-700 hover:border-blue-400 hover:text-blue-700 transition-colors';
        chip.setAttribute('data-genre', genre.name);
        chip.textContent = genre.name;
        chip.addEventListener('click', () => toggleMGMGenre(genre.name, chip));
        container.appendChild(chip);
    });
}

function toggleMGMGenre(genreName, chipEl) {
    const idx = mgmSelectedGenres.indexOf(genreName);
    if (idx >= 0) {
        mgmSelectedGenres.splice(idx, 1);
        chipEl.classList.remove('border-blue-500', 'bg-blue-50', 'text-blue-700');
        chipEl.classList.add('border-gray-300', 'bg-white', 'text-gray-700');
    } else {
        if (mgmSelectedGenres.length >= 5) { showToast('error', 'Maximum 5 genres allowed'); return; }
        mgmSelectedGenres.push(genreName);
        chipEl.classList.add('border-blue-500', 'bg-blue-50', 'text-blue-700');
        chipEl.classList.remove('border-gray-300', 'bg-white', 'text-gray-700');
    }
    const countEl = document.getElementById('mgm-genre-count');
    if (countEl) countEl.textContent = mgmSelectedGenres.length;
    const btn = document.getElementById('create-mgm-playlist-btn');
    if (btn) btn.disabled = mgmSelectedGenres.length < 2;
}

document.addEventListener('DOMContentLoaded', function() {
    const mgmForm = document.getElementById('multi-genre-mix-form');
    if (mgmForm) {
        mgmForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (!checkLibrarySelection()) return;
            if (mgmSelectedGenres.length < 2) { showToast('error', 'Please select at least 2 genres'); return; }
            const btn = document.getElementById('create-mgm-playlist-btn');
            btn.disabled = true;
            showToast('loading', 'Creating your Multi Genre Mix...', 0);
            try {
                const refreshFrequency = document.querySelector('input[name="mgm-refresh-frequency"]:checked').value;
                const playlistLength = parseInt(document.querySelector('input[name="mgm-playlist-length"]:checked').value);
                const response = await fetch('/api/create-multi-genre-mix', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ genres: mgmSelectedGenres, refresh_frequency: refreshFrequency, playlist_length: playlistLength, library_ids: selectedLibraryIds })
                });
                if (!response.ok) { const err = await response.json().catch(() => ({ detail: 'Unknown error' })); throw new Error(err.detail || 'Failed'); }
                const data = await response.json();
                showToast('success', `Multi Genre Mix created with ${data.songs ? data.songs.length : playlistLength} tracks`);
                updatePlaylistCount();
            } catch (error) { showToast('error', error.message); }
            finally { btn.disabled = mgmSelectedGenres.length < 2; }
        });
    }
});

// ============================================================
// DECADE DISCOVERY
// ============================================================

const DECADE_OPTIONS = ['60s', '70s', '80s', '90s', '00s', '10s', '20s'];

function initDecadeChips() {
    const container = document.getElementById('dd-decade-chips');
    if (!container || container.querySelectorAll('.dd-chip').length > 0) return;
    DECADE_OPTIONS.forEach(decade => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'dd-chip px-4 py-2 rounded-full text-sm border border-gray-300 bg-white text-gray-700 hover:border-blue-400 hover:text-blue-700 transition-colors';
        chip.setAttribute('data-decade', decade);
        chip.textContent = decade;
        chip.addEventListener('click', () => toggleDDDecade(decade, chip));
        container.appendChild(chip);
    });
}

function toggleDDDecade(decade, chipEl) {
    const idx = ddSelectedDecades.indexOf(decade);
    if (idx >= 0) {
        ddSelectedDecades.splice(idx, 1);
        chipEl.classList.remove('border-blue-500', 'bg-blue-50', 'text-blue-700');
        chipEl.classList.add('border-gray-300', 'bg-white', 'text-gray-700');
    } else {
        ddSelectedDecades.push(decade);
        chipEl.classList.add('border-blue-500', 'bg-blue-50', 'text-blue-700');
        chipEl.classList.remove('border-gray-300', 'bg-white', 'text-gray-700');
    }
    const btn = document.getElementById('create-dd-playlist-btn');
    if (btn) btn.disabled = ddSelectedDecades.length === 0;
}

document.addEventListener('DOMContentLoaded', function() {
    const ddForm = document.getElementById('decade-discovery-form');
    if (ddForm) {
        ddForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (!checkLibrarySelection()) return;
            if (ddSelectedDecades.length === 0) { showToast('error', 'Please select at least one decade'); return; }
            const btn = document.getElementById('create-dd-playlist-btn');
            btn.disabled = true;
            showToast('loading', 'Creating your Decade playlist...', 0);
            try {
                const mode = document.querySelector('input[name="dd-mode"]:checked').value;
                const refreshFrequency = document.querySelector('input[name="dd-refresh-frequency"]:checked').value;
                const playlistLength = parseInt(document.querySelector('input[name="dd-playlist-length"]:checked').value);
                const response = await fetch('/api/create-decade-discovery', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ decades: ddSelectedDecades, mode: mode, refresh_frequency: refreshFrequency, playlist_length: playlistLength, library_ids: selectedLibraryIds })
                });
                if (!response.ok) { const err = await response.json().catch(() => ({ detail: 'Unknown error' })); throw new Error(err.detail || 'Failed'); }
                const data = await response.json();
                showToast('success', `Decade playlist created with ${data.songs ? data.songs.length : playlistLength} tracks`);
                updatePlaylistCount();
            } catch (error) { showToast('error', error.message); }
            finally { btn.disabled = ddSelectedDecades.length === 0; }
        });
    }
});

// ============================================================
// SONIC JOURNEY
// ============================================================

async function loadArtistsForSJ() {
    if (allArtists.length === 0) {
        try {
            const url = selectedLibraryIds.length > 0
                ? `/api/artists?library_ids=${selectedLibraryIds.join(',')}`
                : '/api/artists';
            const response = await fetch(url);
            if (response.ok) allArtists = await response.json();
        } catch (e) { console.error('Failed to load artists for SJ:', e); return; }
    }
    ['sj-start-artist-select', 'sj-end-artist-select'].forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;
        while (select.options.length > 1) select.remove(1);
        allArtists.forEach(artist => {
            const opt = document.createElement('option');
            opt.value = artist.id;
            opt.textContent = artist.name;
            select.appendChild(opt);
        });
    });
    const startSel = document.getElementById('sj-start-artist-select');
    const endSel = document.getElementById('sj-end-artist-select');
    if (startSel) startSel.onchange = function() { sjStartArtistId = this.value || null; updateSJSubmitButton(); };
    if (endSel) endSel.onchange = function() { sjEndArtistId = this.value || null; updateSJSubmitButton(); };
}

function updateSJSubmitButton() {
    const btn = document.getElementById('create-sj-playlist-btn');
    if (btn) btn.disabled = !(sjStartArtistId && sjEndArtistId && sjStartArtistId !== sjEndArtistId);
}

document.addEventListener('DOMContentLoaded', function() {
    const sjForm = document.getElementById('sonic-journey-form');
    if (sjForm) {
        sjForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (!checkLibrarySelection()) return;
            if (!sjStartArtistId || !sjEndArtistId) { showToast('error', 'Please select both a start and end artist'); return; }
            if (sjStartArtistId === sjEndArtistId) { showToast('error', 'Start and end artists must be different'); return; }
            const btn = document.getElementById('create-sj-playlist-btn');
            btn.disabled = true;
            showToast('loading', 'Building your Sonic Journey — this may take a moment...', 0);
            try {
                const refreshFrequency = document.querySelector('input[name="sj-refresh-frequency"]:checked').value;
                const playlistLength = parseInt(document.querySelector('input[name="sj-playlist-length"]:checked').value);
                const response = await fetch('/api/create-sonic-journey', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start_artist_id: sjStartArtistId, end_artist_id: sjEndArtistId, refresh_frequency: refreshFrequency, playlist_length: playlistLength, library_ids: selectedLibraryIds })
                });
                if (!response.ok) { const err = await response.json().catch(() => ({ detail: 'Unknown error' })); throw new Error(err.detail || 'Failed'); }
                const data = await response.json();
                showToast('success', `Sonic Journey created with ${data.songs ? data.songs.length : playlistLength} tracks`);
                updatePlaylistCount();
            } catch (error) { showToast('error', error.message); }
            finally { updateSJSubmitButton(); }
        });
    }
});

// ============================================================
// GENRE ARCHAEOLOGY
// ============================================================

async function loadGenresForGA() {
    if (allGenres.length === 0) {
        try {
            const url = selectedLibraryIds.length > 0
                ? `/api/genres?library_ids=${selectedLibraryIds.join(',')}`
                : '/api/genres';
            const response = await fetch(url);
            if (response.ok) allGenres = await response.json();
        } catch (e) { console.error('Failed to load genres for GA:', e); return; }
    }
    const select = document.getElementById('ga-genre-select');
    if (!select) return;
    while (select.options.length > 1) select.remove(1);
    allGenres.forEach(genre => {
        const opt = document.createElement('option');
        opt.value = genre.name;
        opt.textContent = `${genre.name} (${genre.songCount})`;
        select.appendChild(opt);
    });
    select.onchange = function() {
        gaSelectedGenre = this.value || null;
        const btn = document.getElementById('create-ga-playlist-btn');
        if (btn) btn.disabled = !gaSelectedGenre;
    };
}

document.addEventListener('DOMContentLoaded', function() {
    const gaForm = document.getElementById('genre-archaeology-form');
    if (gaForm) {
        gaForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (!checkLibrarySelection()) return;
            if (!gaSelectedGenre) { showToast('error', 'Please select a genre'); return; }
            const btn = document.getElementById('create-ga-playlist-btn');
            btn.disabled = true;
            showToast('loading', 'Digging through your genre history...', 0);
            try {
                const digDepth = document.querySelector('input[name="ga-dig-depth"]:checked').value;
                const refreshFrequency = document.querySelector('input[name="ga-refresh-frequency"]:checked').value;
                const playlistLength = parseInt(document.querySelector('input[name="ga-playlist-length"]:checked').value);
                const response = await fetch('/api/create-genre-archaeology', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ genre: gaSelectedGenre, dig_depth: digDepth, refresh_frequency: refreshFrequency, playlist_length: playlistLength, library_ids: selectedLibraryIds })
                });
                if (!response.ok) { const err = await response.json().catch(() => ({ detail: 'Unknown error' })); throw new Error(err.detail || 'Failed'); }
                const data = await response.json();
                showToast('success', `Archaeology playlist created with ${data.songs ? data.songs.length : playlistLength} tracks`);
                updatePlaylistCount();
            } catch (error) { showToast('error', error.message); }
            finally { btn.disabled = !gaSelectedGenre; }
        });
    }
});
