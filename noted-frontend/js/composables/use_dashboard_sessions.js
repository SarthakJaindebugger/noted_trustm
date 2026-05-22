import { ref, computed, watch } from 'vue';
import { sessionService } from '../services/session_service.js';

export function useDashboardSessions() {
    const sessions = ref([]);
    const sessionsById = ref(new Map());
    const sessionsByReference = ref(new Map());
    const filteredSessions = ref([]);
    const searchQuery = ref('');
    const selectedSessions = ref([]);
    const itemsPerPage = ref(10);
    const pageSizeOptions = [2, 5, 10, 25, 50, 100];
    const currentPage = ref(1);
    const isLoading = ref(false);
    const sortField = ref('date');
    const sortDirection = ref('desc');
    const showDropdownId = ref(null);
    const currentView = ref('sessions-list');
    const selectedSession = ref(null);
    const pendingSessionToOpen = ref(null);
    const isOpeningSession = ref(false);

    const selectedSessionRef = computed(() => selectedSession.value?.reference ?? null);
    const selectedSessionDbId = computed(() => selectedSession.value?.id ?? null);

    const paginatedSessions = computed(() => {
        if (filteredSessions.value.length === 0) {
            return [];
        }

        const startIndex = (currentPage.value - 1) * itemsPerPage.value;
        return filteredSessions.value.slice(startIndex, startIndex + itemsPerPage.value);
    });

    const totalPages = computed(() => (
        filteredSessions.value.length === 0
            ? 1
            : Math.ceil(filteredSessions.value.length / itemsPerPage.value)
    ));

    const pageDisplayRange = computed(() => {
        const total = filteredSessions.value.length;
        if (total === 0) {
            return { start: 0, end: 0 };
        }

        const safePage = Math.min(Math.max(currentPage.value, 1), totalPages.value);
        const start = (safePage - 1) * itemsPerPage.value + 1;
        const visibleCount = paginatedSessions.value.length
            || Math.min(itemsPerPage.value, Math.max(total - start + 1, 0));
        const rawEnd = start + visibleCount - 1;

        return {
            start: Math.min(start, total),
            end: Math.min(Math.max(rawEnd, start), total),
        };
    });

    const visibleSelectionState = computed(() => {
        const visibleIds = paginatedSessions.value.map(session => session.id);

        if (visibleIds.length === 0) {
            return { allSelected: false, partiallySelected: false };
        }

        const selectedVisibleCount = visibleIds.reduce(
            (count, id) => count + (selectedSessions.value.includes(id) ? 1 : 0),
            0
        );

        return {
            allSelected: selectedVisibleCount === visibleIds.length,
            partiallySelected: selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length,
        };
    });

    const indexSessions = (sessionList = []) => {
        const byId = new Map();
        const byReference = new Map();

        sessionList.forEach(session => {
            if (session.id) {
                byId.set(session.id, session);
            }
            if (session.reference) {
                byReference.set(session.reference, session);
            }
        });

        sessionsById.value = byId;
        sessionsByReference.value = byReference;
    };

    const resolveSession = (identifier) => {
        if (!identifier) {
            return null;
        }

        if (typeof identifier === 'object') {
            return identifier;
        }

        return sessionsById.value.get(identifier) || sessionsByReference.value.get(identifier) || null;
    };

    const setSelectedSession = (sessionLike) => {
        const session = resolveSession(sessionLike);
        if (!session) {
            selectedSession.value = null;
            return null;
        }

        selectedSession.value = session;
        return session;
    };

    const filterSessions = () => {
        const query = searchQuery.value.trim().toLowerCase();

        const filtered = sessions.value
            .filter(session => {
                if (!query) {
                    return true;
                }

                return session.reference.toLowerCase().includes(query)
                    || session.topic.toLowerCase().includes(query);
            })
            .sort((left, right) => {
                let leftValue = left[sortField.value];
                let rightValue = right[sortField.value];

                if (sortField.value === 'date') {
                    leftValue = new Date(left.created_at);
                    rightValue = new Date(right.created_at);
                }

                if (sortDirection.value === 'asc') {
                    return leftValue < rightValue ? -1 : leftValue > rightValue ? 1 : 0;
                }

                return leftValue > rightValue ? -1 : leftValue < rightValue ? 1 : 0;
            });

        filteredSessions.value = filtered;
        currentPage.value = 1;
    };

    const applySessionUpdate = (updatedSession) => {
        if (!updatedSession?.id) {
            return;
        }

        const sessionIndex = sessions.value.findIndex(session => session.id === updatedSession.id);
        if (sessionIndex === -1) {
            sessions.value = [...sessions.value, updatedSession];
        } else {
            sessions.value[sessionIndex] = {
                ...sessions.value[sessionIndex],
                ...updatedSession,
            };
            sessions.value = [...sessions.value];
        }

        const previousPage = currentPage.value;
        indexSessions(sessions.value);
        filterSessions();

        if (currentView.value === 'sessions-list') {
            currentPage.value = Math.min(previousPage, totalPages.value);
        }

        if (selectedSession.value?.id === updatedSession.id) {
            selectedSession.value = resolveSession(updatedSession.id) || updatedSession;
        }
    };

    const searchSessions = () => {
        filterSessions();
    };

    const sortBy = (field) => {
        if (sortField.value === field) {
            sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
        } else {
            sortField.value = field;
            sortDirection.value = 'asc';
        }

        filterSessions();
    };

    const toggleDropdown = (sessionId) => {
        showDropdownId.value = showDropdownId.value === sessionId ? null : sessionId;
    };

    const closeDropdown = () => {
        showDropdownId.value = null;
    };

    const toggleSessionSelection = (sessionId) => {
        const index = selectedSessions.value.indexOf(sessionId);
        if (index > -1) {
            selectedSessions.value.splice(index, 1);
            return;
        }

        selectedSessions.value.push(sessionId);
    };

    const selectAllSessions = () => {
        const visibleIds = paginatedSessions.value.map(session => session.id);
        if (visibleIds.length === 0) {
            return;
        }

        if (visibleSelectionState.value.allSelected) {
            selectedSessions.value = selectedSessions.value.filter(id => !visibleIds.includes(id));
            return;
        }

        const updatedSelections = new Set(selectedSessions.value);
        visibleIds.forEach(id => updatedSelections.add(id));
        selectedSessions.value = Array.from(updatedSelections);
    };

    const goToPage = (pageNumber) => {
        if (filteredSessions.value.length === 0) {
            currentPage.value = 1;
            return;
        }

        if (pageNumber < 1 || pageNumber > totalPages.value) {
            return;
        }

        currentPage.value = pageNumber;
    };

    const goToFirstPage = () => goToPage(1);
    const goToLastPage = () => goToPage(totalPages.value);
    const nextPage = () => goToPage(currentPage.value + 1);
    const prevPage = () => goToPage(currentPage.value - 1);

    const loadSessions = async () => {
        isLoading.value = true;

        try {
            const fetchedSessions = await sessionService.getUserSessions();
            sessions.value = fetchedSessions;
            indexSessions(fetchedSessions);

            if (selectedSession.value) {
                const refreshedSession = resolveSession(selectedSession.value.id)
                    || resolveSession(selectedSession.value.reference);
                selectedSession.value = refreshedSession || null;
            }

            filterSessions();
        } catch (error) {
            console.error('Failed to load sessions:', error);
        } finally {
            isLoading.value = false;
        }
    };

    watch(itemsPerPage, () => {
        currentPage.value = 1;
    });

    watch(
        () => filteredSessions.value.length,
        () => {
            if (filteredSessions.value.length === 0) {
                currentPage.value = 1;
                return;
            }

            if (currentPage.value > totalPages.value) {
                currentPage.value = totalPages.value;
            }
        }
    );

    return {
        sessions,
        sessionsById,
        sessionsByReference,
        filteredSessions,
        searchQuery,
        selectedSessions,
        itemsPerPage,
        pageSizeOptions,
        currentPage,
        paginatedSessions,
        totalPages,
        pageDisplayRange,
        visibleSelectionState,
        isLoading,
        sortField,
        sortDirection,
        showDropdownId,
        currentView,
        selectedSession,
        selectedSessionRef,
        selectedSessionDbId,
        pendingSessionToOpen,
        isOpeningSession,
        resolveSession,
        setSelectedSession,
        filterSessions,
        applySessionUpdate,
        searchSessions,
        sortBy,
        toggleDropdown,
        closeDropdown,
        toggleSessionSelection,
        selectAllSessions,
        goToPage,
        goToFirstPage,
        goToLastPage,
        nextPage,
        prevPage,
        loadSessions,
    };
}
