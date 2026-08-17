import { ref, nextTick, computed, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { apiClient } from '../services/api_client.js';
import { languageService } from '../services/language_service.js';

export default {
  name: 'AdminDashboard',

  setup() {
    const router = useRouter();

    // ── Dashboard fields (all questionnaire keys) ──
    const totalForms        = ref(0);
    const numberOfCustomers = ref('—');
    const averageConvTime   = ref('—');
    const contactMethods    = ref([]);
    const topicsDiscussed   = ref([]);
    const purposesOfVisit   = ref([]);
    const labourPositions   = ref([]);
    const birthCountries    = ref([]);
    const languages         = ref([]);
    const residences        = ref([]);
    const durationResidence = ref([]);
    const directedTo        = ref([]);
    const heardFrom         = ref([]);
    const immigrationReasons= ref([]);
    const educationLevels   = ref([]);
    const additionalInfoTags= ref([]);
    const additionalInfoTextTags = ref([]);
    const otherFeedback     = ref([]);
    const faqs              = ref([]);
    const isGeneratingFaqs  = ref(false);
    const ageGroups         = ref({});
    const genderCounts      = ref({});
    const birthCountryCounts = ref({});
    const fieldCounts       = ref({});
    const genderBreakdown   = ref({});

    // ── CRM Modal state ──
    const showCrmModal       = ref(false);
    const crmForms           = ref([]);
    const selectedCrmPaths   = reactive(new Set());
    const isLoadingCrmForms  = ref(false);

    const crmSelectAllChecked = computed(() =>
      crmForms.value.length > 0 && crmForms.value.every(f => selectedCrmPaths.has(f.file_path))
    );
    const crmSelectAllIndeterminate = computed(() =>
      selectedCrmPaths.size > 0 && !crmSelectAllChecked.value
    );

    // ── Floating chat state ──
    const messages = ref([{
      role: 'assistant',
      content: '👋 Hello! I\'m your AI immigration assistant. What would you like to know?',
      timestamp: Date.now()
    }]);
    const newMessage      = ref('');
    const isTyping        = ref(false);
    const isMinimized     = ref(false);
    const messagesContainer = ref(null);
    const unreadCount     = ref(0);
    let   _unread         = 0;


    const scrollToBottom = async () => {
      await nextTick();
      if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    };
    const formatTime = ts => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const getRAGResponse = async (query) => {
      const token = authService.getToken();
      const apiUrl = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://127.0.0.1:8000/api/v1/rag/query' : '/api/rag/query';
      const resp = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
        body: JSON.stringify({ query, top_k: 5 })
      });
      if (!resp.ok) throw new Error(`RAG API error: ${resp.status}`);
      return (await resp.json()).response;
    };

    const sendMessage = async () => {
      const content = newMessage.value.trim();
      if (!content || isTyping.value) return;
      messages.value.push({ role: 'user', content, timestamp: Date.now() });
      newMessage.value = '';
      await scrollToBottom();
      isTyping.value = true;
      try {
        const reply = await getRAGResponse(content);
        messages.value.push({ role: 'assistant', content: reply, timestamp: Date.now() });
        if (isMinimized.value) { _unread++; unreadCount.value = _unread; }
        await scrollToBottom();
      } catch {
        messages.value.push({ role: 'assistant', content: 'Error fetching response. Try again.', timestamp: Date.now() });
      } finally { isTyping.value = false; }
    };

    const clearConversation = () => {
      messages.value = [{ role: 'assistant', content: '✨ Conversation cleared.', timestamp: Date.now() }];
      _unread = 0; unreadCount.value = 0; scrollToBottom();
    };
    const expandChat = () => { isMinimized.value = false; _unread = 0; unreadCount.value = 0; scrollToBottom(); };
    const logout = async () => { authService.logout(); localStorage.removeItem('isAdmin'); router.push({ name: 'login' }); };


    // ── Load aggregated CRM data on mount ──
    const fetchAggregatedCrmData = async () => {
      try {
        const d = await apiClient.get('/admin/crm-forms/aggregated');
        totalForms.value         = d.total_forms        || 0;
        numberOfCustomers.value  = d.number_of_customers || d.total_forms || '—';
        averageConvTime.value    = d.average_conversation_time || '—';
        contactMethods.value     = d.contact_methods    || [];
        topicsDiscussed.value    = d.topics_discussed   || [];
        purposesOfVisit.value    = d.purposes_of_visit  || [];
        labourPositions.value    = d.labour_positions   || [];
        birthCountries.value     = d.birth_countries    || [];
        languages.value          = d.languages          || [];
        residences.value         = d.residences         || [];
        durationResidence.value  = d.duration_of_residence || [];
        directedTo.value         = d.directed_to        || [];
        heardFrom.value          = d.heard_from         || [];
        immigrationReasons.value = d.immigration_reasons || [];
        educationLevels.value    = d.education_levels   || [];
        additionalInfoTags.value = d.additional_info_tags || [];
        additionalInfoTextTags.value = d.additional_info_text_tags || [];
        otherFeedback.value      = d.other_feedback     || [];
        ageGroups.value          = d.age_groups         || {};
        genderCounts.value       = d.gender_counts      || {};
        birthCountryCounts.value = d.birth_country_counts || {};
        fieldCounts.value        = d.field_counts       || {};
        customerComingFromCounts.value = d.customer_coming_from_counts || {};
        genderBreakdown.value = d.gender_breakdown || {};
      } catch (err) { console.error('Error fetching aggregated CRM data', err); }
    };

    fetchAggregatedCrmData();

    const combinedInsightTags = computed(() => {
      const merged = new Set([...additionalInfoTextTags.value, ...otherFeedback.value]);
      return [...merged].sort();
    });

    const generateFaqs = async () => {
      isGeneratingFaqs.value = true;
      try {
        const result = await apiClient.post('/admin/generate-faqs');
        faqs.value = result.faqs || [];
      } catch (err) {
        console.error('Failed to generate FAQs', err);
        alert('Failed to generate FAQs.');
      } finally {
        isGeneratingFaqs.value = false;
      }
    };

    // Load existing FAQs on mount
    apiClient.get('/admin/faqs').then(d => { faqs.value = d.faqs || []; }).catch(() => {});

    // ── CRM modal ──
    const openCrmModal = async () => {
      showCrmModal.value = true;
      isLoadingCrmForms.value = true;
      selectedCrmPaths.clear();
      try {
        const resp = await apiClient.get('/admin/crm-forms');
        crmForms.value = (resp.crm_forms || []).sort((a, b) => {
          return `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`);
        });
      } catch (err) { console.error('Failed to load CRM forms', err); crmForms.value = []; }
      finally { isLoadingCrmForms.value = false; }
    };
    const closeCrmModal = () => { showCrmModal.value = false; selectedCrmPaths.clear(); };
    const toggleCrmFormSelection = fp => selectedCrmPaths.has(fp) ? selectedCrmPaths.delete(fp) : selectedCrmPaths.add(fp);
    const toggleCrmSelectAll = () => {
      if (crmSelectAllChecked.value) selectedCrmPaths.clear();
      else crmForms.value.forEach(f => selectedCrmPaths.add(f.file_path));
    };

    // Parse selected forms and apply result directly to dashboard fields
    const parseCrmForms = async () => {
      if (selectedCrmPaths.size === 0) { alert('Please select at least one CRM form.'); return; }
      try {
        const d = await apiClient.post('/admin/crm-forms/parse', { file_paths: Array.from(selectedCrmPaths) });
        // Apply parsed data directly — replaces dashboard with data from selected forms only
        totalForms.value         = d.total_forms        || 0;
        numberOfCustomers.value  = d.number_of_customers || d.total_forms || '—';
        averageConvTime.value    = d.average_conversation_time || '—';
        contactMethods.value     = d.contact_methods    || [];
        topicsDiscussed.value    = d.topics_discussed   || [];
        purposesOfVisit.value    = d.purposes_of_visit  || [];
        labourPositions.value    = d.labour_positions   || [];
        birthCountries.value     = d.birth_countries    || [];
        languages.value          = d.languages          || [];
        residences.value         = d.residences         || [];
        durationResidence.value  = d.duration_of_residence || [];
        directedTo.value         = d.directed_to        || [];
        heardFrom.value          = d.heard_from         || [];
        immigrationReasons.value = d.immigration_reasons || [];
        educationLevels.value    = d.education_levels   || [];
        additionalInfoTags.value = d.additional_info_tags || [];
        additionalInfoTextTags.value = d.additional_info_text_tags || [];
        otherFeedback.value      = d.other_feedback     || [];
        ageGroups.value          = d.age_groups         || {};
        genderCounts.value       = d.gender_counts      || {};
        birthCountryCounts.value = d.birth_country_counts || {};
        fieldCounts.value        = d.field_counts       || {};
        customerComingFromCounts.value = d.customer_coming_from_counts || {};
        genderBreakdown.value = d.gender_breakdown || {};
        closeCrmModal();
      } catch (err) { console.error('Failed to parse CRM forms', err); alert('Failed to parse CRM forms.'); }
    };


    const clearUserDatabase = async () => {
      if (!confirm('Are you sure you want to clear ALL user data? This will delete all files from every user folder and all submitted CRM forms. This action cannot be undone.')) return;
      try {
        const result = await apiClient.delete('/admin/clear-user-database');
        alert(`Database cleared:\n• ${result.deleted_files} user files deleted\n• ${result.crm_forms_deleted} CRM forms deleted\n• Users affected: ${result.users_cleared.join(', ') || 'none'}`);
        fetchAggregatedCrmData();
      } catch (err) { console.error('Failed to clear database', err); alert('Failed to clear user database.'); }
    };

    const customerComingFromCounts = ref({});
    const ageGroupMax = computed(() => Math.max(1, ...Object.values(ageGroups.value || {})));
    const genderTotal = computed(() => (genderCounts.value.Male || 0) + (genderCounts.value.Female || 0));
    const birthCountryMax = computed(() => Math.max(1, ...Object.values(birthCountryCounts.value || {})));
    const customerComingFromMax = computed(() => Math.max(1, ...Object.values(customerComingFromCounts.value || {})));

    const showLangDropdown = ref(false);
    const uiLanguages = languageService.LANGUAGES;
    const currentLanguage = languageService.currentLanguage;
    const changeLanguage = async (code) => { showLangDropdown.value = false; await languageService.setLanguage(code); };
    const getLanguageLabel = languageService.getLanguageLabel;

    const showProfileMenu = ref(false);
    const userInitial = computed(() => (authService.getUser()?.username || 'A')[0].toUpperCase());
    const switchToUser = async () => {
      await authService.switchRole('user');
      router.push({ name: 'dashboard' });
    };

    const getGenderBar = (fieldKey, label) => {
      const bd = genderBreakdown.value[fieldKey];
      if (!bd || !bd[label]) return null;
      const d = bd[label];
      const total = (d.Male || 0) + (d.Female || 0) + (d.Unknown || 0);
      if (total === 0) return null;
      return { m: d.Male || 0, f: d.Female || 0, u: d.Unknown || 0, total };
    };

    return {
      logout, totalForms, numberOfCustomers, averageConvTime,
      contactMethods, topicsDiscussed, purposesOfVisit, labourPositions,
      birthCountries, languages, residences, durationResidence,
      directedTo, heardFrom, immigrationReasons, educationLevels,
      additionalInfoTags, additionalInfoTextTags, otherFeedback, combinedInsightTags,
      faqs, isGeneratingFaqs, generateFaqs, ageGroups, ageGroupMax,
      genderCounts, genderTotal, birthCountryCounts, birthCountryMax, fieldCounts,
      customerComingFromCounts, customerComingFromMax,
      genderBreakdown, getGenderBar,
      showCrmModal, crmForms, selectedCrmPaths, isLoadingCrmForms,
      crmSelectAllChecked, crmSelectAllIndeterminate,
      showLangDropdown, uiLanguages, currentLanguage, changeLanguage, getLanguageLabel,
      showProfileMenu, userInitial, switchToUser,
      openCrmModal, closeCrmModal, toggleCrmFormSelection, toggleCrmSelectAll, parseCrmForms, clearUserDatabase,
      messages, newMessage, isTyping, isMinimized, unreadCount, messagesContainer,
      sendMessage, clearConversation, formatTime, expandChat,
    };
  },

  template: `
  <div class="min-h-screen bg-gray-50">

    <!-- ── Header ── -->
    <div class="sticky top-0 z-10 bg-white border-b border-gray-200">
      <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-semibold text-slate-800">Admin Dashboard</h1>
          <p class="text-slate-500 text-sm">Aggregated from {{ totalForms }} submitted CRM form(s)</p>
        </div>
        <div class="flex gap-3 items-center">
          <!-- Language Selector -->
          <div class="relative notranslate" translate="no">
            <button @click="showLangDropdown = !showLangDropdown"
              class="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-sm text-slate-600 hover:bg-gray-50 transition">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"/></svg>
              {{ getLanguageLabel() }}
            </button>
            <div v-if="showLangDropdown" class="absolute right-0 mt-2 w-44 bg-white rounded-lg shadow-lg border border-gray-200 py-1 max-h-64 overflow-y-auto z-30">
              <button v-for="lang in uiLanguages" :key="lang.code"
                @click="changeLanguage(lang.code)"
                :class="['w-full text-left px-4 py-2 text-sm hover:bg-gray-50 transition', currentLanguage === lang.code ? 'text-blue-600 font-medium bg-blue-50' : 'text-slate-700']">
                {{ lang.label }}
              </button>
            </div>
          </div>
          <button @click="openCrmModal" class="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition text-sm font-medium">
            Analyze CRM Forms
          </button>
          <button @click="clearUserDatabase" class="px-4 py-2 rounded-lg border border-gray-200 text-slate-600 hover:bg-gray-50 transition text-sm font-medium">
            Clear User Database
          </button>
          <!-- Profile Icon -->
          <div class="relative">
            <button @click="showProfileMenu = !showProfileMenu"
              class="w-9 h-9 rounded-full bg-slate-800 text-white flex items-center justify-center text-sm font-semibold hover:bg-slate-700 transition">
              {{ userInitial }}
            </button>
            <div v-if="showProfileMenu" class="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-30">
              <button @click="switchToUser" class="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-gray-50 transition">Switch to User</button>
              <button @click="logout" class="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition">Logout</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Dashboard grid ── -->
    <div class="max-w-7xl mx-auto p-6 space-y-6">

      <!-- Summary row -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">Total Forms</div>
          <div class="text-3xl font-bold text-slate-800">{{ totalForms }}</div>
        </div>
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">Service Advisors</div>
          <div class="text-3xl font-bold text-slate-800">{{ numberOfCustomers }}</div>
        </div>
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">Avg. Conv. Time</div>
          <div class="text-xl font-semibold text-slate-800 mt-1">{{ averageConvTime }}</div>
        </div>
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-1">Languages Detected</div>
          <div class="text-3xl font-bold text-slate-800">{{ languages.length }}</div>
        </div>
      </div>


      <!-- Full questionnaire fields grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

        <!-- Contact Method — table with M/F -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q5 · Contact Method</div>
          <div v-if="fieldCounts.contact_methods && Object.keys(fieldCounts.contact_methods).length" class="overflow-y-auto" style="max-height: 200px;">
            <table class="w-full text-xs">
              <thead><tr class="border-b border-gray-100"><th class="text-left py-1 text-gray-500">Method</th><th class="py-1 text-gray-500 w-20 text-center">M / F</th><th class="text-right py-1 text-gray-500 w-10">N</th></tr></thead>
              <tbody>
                <tr v-for="(count, label) in fieldCounts.contact_methods" :key="label" class="border-b border-gray-50">
                  <td class="py-1.5 text-gray-700">{{ label }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="getGenderBar('contact_methods', label)" class="inline-flex items-center gap-0.5">
                      <span class="text-blue-600 font-semibold">{{ getGenderBar('contact_methods', label).m }}</span>
                      <span class="text-gray-300">/</span>
                      <span class="text-slate-800 font-semibold">{{ getGenderBar('contact_methods', label).f }}</span>
                    </span>
                    <span v-else class="text-gray-300">—</span>
                  </td>
                  <td class="py-1.5 text-right font-bold text-slate-800">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Heard From — table with M/F -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q6 · Heard From</div>
          <div v-if="fieldCounts.heard_from && Object.keys(fieldCounts.heard_from).length" class="overflow-y-auto" style="max-height: 200px;">
            <table class="w-full text-xs">
              <thead><tr class="border-b border-gray-100"><th class="text-left py-1 text-gray-500">Source</th><th class="py-1 text-gray-500 w-20 text-center">M / F</th><th class="text-right py-1 text-gray-500 w-10">N</th></tr></thead>
              <tbody>
                <tr v-for="(count, label) in fieldCounts.heard_from" :key="label" class="border-b border-gray-50">
                  <td class="py-1.5 text-gray-700">{{ label }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="getGenderBar('heard_from', label)" class="inline-flex items-center gap-0.5">
                      <span class="text-blue-600 font-semibold">{{ getGenderBar('heard_from', label).m }}</span>
                      <span class="text-gray-300">/</span>
                      <span class="text-slate-800 font-semibold">{{ getGenderBar('heard_from', label).f }}</span>
                    </span>
                    <span v-else class="text-gray-300">—</span>
                  </td>
                  <td class="py-1.5 text-right font-bold text-slate-800">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Immigration Reason — split M/F bars -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q10 · Reason for Immigration</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="fieldCounts.immigration_reasons && Object.keys(fieldCounts.immigration_reasons).length" class="overflow-y-auto space-y-2" style="max-height: 200px;">
            <div v-for="(count, label) in fieldCounts.immigration_reasons" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-20 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden flex">
                <div v-if="getGenderBar('immigration_reasons', label)" class="h-full bg-blue-600 transition-all duration-500"
                  :style="{ width: (getGenderBar('immigration_reasons', label).m / Math.max(1, ...Object.values(fieldCounts.immigration_reasons)) * 100) + '%' }"></div>
                <div v-if="getGenderBar('immigration_reasons', label)" class="h-full bg-slate-800 transition-all duration-500"
                  :style="{ width: (getGenderBar('immigration_reasons', label).f / Math.max(1, ...Object.values(fieldCounts.immigration_reasons)) * 100) + '%' }"></div>
                <div v-if="!getGenderBar('immigration_reasons', label)" class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / Math.max(1, ...Object.values(fieldCounts.immigration_reasons)) * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Additional Info — split M/F bars -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q11 · Additional Customer Info</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="fieldCounts.additional_info_tags && Object.keys(fieldCounts.additional_info_tags).length" class="overflow-y-auto space-y-2" style="max-height: 200px;">
            <div v-for="(count, label) in fieldCounts.additional_info_tags" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-28 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden flex">
                <div v-if="getGenderBar('additional_info_tags', label)" class="h-full bg-blue-600 transition-all duration-500"
                  :style="{ width: (getGenderBar('additional_info_tags', label).m / Math.max(1, ...Object.values(fieldCounts.additional_info_tags)) * 100) + '%' }"></div>
                <div v-if="getGenderBar('additional_info_tags', label)" class="h-full bg-slate-800 transition-all duration-500"
                  :style="{ width: (getGenderBar('additional_info_tags', label).f / Math.max(1, ...Object.values(fieldCounts.additional_info_tags)) * 100) + '%' }"></div>
                <div v-if="!getGenderBar('additional_info_tags', label)" class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / Math.max(1, ...Object.values(fieldCounts.additional_info_tags)) * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Birth Country — X-Y axis bar chart (full width) -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200 md:col-span-2 xl:col-span-2" style="height: 320px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q12 · Birth Country Distribution</div>
          <div v-if="Object.keys(birthCountryCounts).length" class="h-full flex flex-col" style="max-height: 260px;">
            <!-- Y-axis label -->
            <div class="flex items-end gap-1 flex-1 overflow-x-auto pb-2 border-b-2 border-gray-300 border-l-2 pl-1 ml-6 relative">
              <!-- Y-axis tick marks -->
              <div class="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-xs text-gray-400 -ml-6" style="width: 24px;">
                <span>{{ birthCountryMax }}</span>
                <span>{{ Math.round(birthCountryMax / 2) }}</span>
                <span>0</span>
              </div>
              <!-- Bars -->
              <div v-for="(count, country) in birthCountryCounts" :key="country"
                class="flex flex-col items-center flex-1 min-w-[40px] max-w-[60px] gap-1 justify-end h-full">
                <span class="text-xs font-bold text-slate-800">{{ count }}</span>
                <div class="w-8 bg-blue-600 rounded-t-md transition-all duration-500"
                  :style="{ height: (count / birthCountryMax * 100) + '%' }"></div>
              </div>
            </div>
            <!-- X-axis labels -->
            <div class="flex gap-1 overflow-x-auto pt-1 ml-6">
              <div v-for="(count, country) in birthCountryCounts" :key="country + '-label'"
                class="flex-1 min-w-[40px] max-w-[60px] text-center">
                <span class="text-xs text-gray-500 block truncate" :title="country">{{ country }}</span>
              </div>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Mother Tongue — split M/F bars -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q13 · Mother Tongue / Language</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="fieldCounts.languages && Object.keys(fieldCounts.languages).length" class="overflow-y-auto space-y-2" style="max-height: 200px;">
            <div v-for="(count, label) in fieldCounts.languages" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-20 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden flex">
                <div v-if="getGenderBar('languages', label)" class="h-full bg-blue-600 transition-all duration-500"
                  :style="{ width: (getGenderBar('languages', label).m / Math.max(1, ...Object.values(fieldCounts.languages)) * 100) + '%' }"></div>
                <div v-if="getGenderBar('languages', label)" class="h-full bg-slate-800 transition-all duration-500"
                  :style="{ width: (getGenderBar('languages', label).f / Math.max(1, ...Object.values(fieldCounts.languages)) * 100) + '%' }"></div>
                <div v-if="!getGenderBar('languages', label)" class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / Math.max(1, ...Object.values(fieldCounts.languages)) * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Education Level — table with M/F -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q14 · Education Level</div>
          <div v-if="fieldCounts.education_levels && Object.keys(fieldCounts.education_levels).length" class="overflow-y-auto" style="max-height: 200px;">
            <table class="w-full text-xs">
              <thead><tr class="border-b border-gray-100"><th class="text-left py-1 text-gray-500">Level</th><th class="py-1 text-gray-500 w-20 text-center">M / F</th><th class="text-right py-1 text-gray-500 w-10">N</th></tr></thead>
              <tbody>
                <tr v-for="(count, label) in fieldCounts.education_levels" :key="label" class="border-b border-gray-50">
                  <td class="py-1.5 text-gray-700">{{ label }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="getGenderBar('education_levels', label)" class="inline-flex items-center gap-0.5">
                      <span class="text-blue-600 font-semibold">{{ getGenderBar('education_levels', label).m }}</span>
                      <span class="text-gray-300">/</span>
                      <span class="text-slate-800 font-semibold">{{ getGenderBar('education_levels', label).f }}</span>
                    </span>
                    <span v-else class="text-gray-300">—</span>
                  </td>
                  <td class="py-1.5 text-right font-bold text-slate-800">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Labour Position — split M/F bars -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q15 · Position in Labour Market</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="fieldCounts.labour_positions && Object.keys(fieldCounts.labour_positions).length" class="overflow-y-auto space-y-2" style="max-height: 200px;">
            <div v-for="(count, label) in fieldCounts.labour_positions" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-24 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden flex">
                <div v-if="getGenderBar('labour_positions', label)" class="h-full bg-blue-600 transition-all duration-500"
                  :style="{ width: (getGenderBar('labour_positions', label).m / Math.max(1, ...Object.values(fieldCounts.labour_positions)) * 100) + '%' }"></div>
                <div v-if="getGenderBar('labour_positions', label)" class="h-full bg-slate-800 transition-all duration-500"
                  :style="{ width: (getGenderBar('labour_positions', label).f / Math.max(1, ...Object.values(fieldCounts.labour_positions)) * 100) + '%' }"></div>
                <div v-if="!getGenderBar('labour_positions', label)" class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / Math.max(1, ...Object.values(fieldCounts.labour_positions)) * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Domicile — table with M/F -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q16 · Customer Domicile</div>
          <div v-if="fieldCounts.residences && Object.keys(fieldCounts.residences).length" class="overflow-y-auto" style="max-height: 200px;">
            <table class="w-full text-xs">
              <thead><tr class="border-b border-gray-100"><th class="text-left py-1 text-gray-500">Location</th><th class="py-1 text-gray-500 w-20 text-center">M / F</th><th class="text-right py-1 text-gray-500 w-10">N</th></tr></thead>
              <tbody>
                <tr v-for="(count, label) in fieldCounts.residences" :key="label" class="border-b border-gray-50">
                  <td class="py-1.5 text-gray-700">{{ label }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="getGenderBar('residences', label)" class="inline-flex items-center gap-0.5">
                      <span class="text-blue-600 font-semibold">{{ getGenderBar('residences', label).m }}</span>
                      <span class="text-gray-300">/</span>
                      <span class="text-slate-800 font-semibold">{{ getGenderBar('residences', label).f }}</span>
                    </span>
                    <span v-else class="text-gray-300">—</span>
                  </td>
                  <td class="py-1.5 text-right font-bold text-slate-800">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Duration of Residence — split M/F bars -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q17 · Duration of Residence</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="fieldCounts.duration_of_residence && Object.keys(fieldCounts.duration_of_residence).length" class="overflow-y-auto space-y-2" style="max-height: 200px;">
            <div v-for="(count, label) in fieldCounts.duration_of_residence" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-24 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden flex">
                <div v-if="getGenderBar('duration_of_residence', label)" class="h-full bg-blue-600 transition-all duration-500"
                  :style="{ width: (getGenderBar('duration_of_residence', label).m / Math.max(1, ...Object.values(fieldCounts.duration_of_residence)) * 100) + '%' }"></div>
                <div v-if="getGenderBar('duration_of_residence', label)" class="h-full bg-slate-800 transition-all duration-500"
                  :style="{ width: (getGenderBar('duration_of_residence', label).f / Math.max(1, ...Object.values(fieldCounts.duration_of_residence)) * 100) + '%' }"></div>
                <div v-if="!getGenderBar('duration_of_residence', label)" class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / Math.max(1, ...Object.values(fieldCounts.duration_of_residence)) * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Contents of Visit — split M/F bars (wider) -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200 md:col-span-2 xl:col-span-2" style="height: 300px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q18 · Contents of Customer Visit</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="fieldCounts.topics_discussed && Object.keys(fieldCounts.topics_discussed).length" class="overflow-y-auto space-y-2" style="max-height: 240px;">
            <div v-for="(count, label) in fieldCounts.topics_discussed" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-44 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden flex">
                <div v-if="getGenderBar('topics_discussed', label)" class="h-full bg-blue-600 transition-all duration-500"
                  :style="{ width: (getGenderBar('topics_discussed', label).m / Math.max(1, ...Object.values(fieldCounts.topics_discussed)) * 100) + '%' }"></div>
                <div v-if="getGenderBar('topics_discussed', label)" class="h-full bg-slate-800 transition-all duration-500"
                  :style="{ width: (getGenderBar('topics_discussed', label).f / Math.max(1, ...Object.values(fieldCounts.topics_discussed)) * 100) + '%' }"></div>
                <div v-if="!getGenderBar('topics_discussed', label)" class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / Math.max(1, ...Object.values(fieldCounts.topics_discussed)) * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Purpose of Visit — table with M/F -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q19 · Purpose of Visit</div>
          <div v-if="fieldCounts.purposes_of_visit && Object.keys(fieldCounts.purposes_of_visit).length" class="overflow-y-auto" style="max-height: 200px;">
            <table class="w-full text-xs">
              <thead><tr class="border-b border-gray-100"><th class="text-left py-1 text-gray-500">Purpose</th><th class="py-1 text-gray-500 w-20 text-center">M / F</th><th class="text-right py-1 text-gray-500 w-10">N</th></tr></thead>
              <tbody>
                <tr v-for="(count, label) in fieldCounts.purposes_of_visit" :key="label" class="border-b border-gray-50">
                  <td class="py-1.5 text-gray-700">{{ label }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="getGenderBar('purposes_of_visit', label)" class="inline-flex items-center gap-0.5">
                      <span class="text-blue-600 font-semibold">{{ getGenderBar('purposes_of_visit', label).m }}</span>
                      <span class="text-gray-300">/</span>
                      <span class="text-slate-800 font-semibold">{{ getGenderBar('purposes_of_visit', label).f }}</span>
                    </span>
                    <span v-else class="text-gray-300">—</span>
                  </td>
                  <td class="py-1.5 text-right font-bold text-slate-800">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Where Directed — table with M/F -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Q21 · Where Customer Is Directed</div>
          <div v-if="fieldCounts.directed_to && Object.keys(fieldCounts.directed_to).length" class="overflow-y-auto" style="max-height: 200px;">
            <table class="w-full text-xs">
              <thead><tr class="border-b border-gray-100"><th class="text-left py-1 text-gray-500">Destination</th><th class="py-1 text-gray-500 w-20 text-center">M / F</th><th class="text-right py-1 text-gray-500 w-10">N</th></tr></thead>
              <tbody>
                <tr v-for="(count, label) in fieldCounts.directed_to" :key="label" class="border-b border-gray-50">
                  <td class="py-1.5 text-gray-700">{{ label }}</td>
                  <td class="py-1.5 text-center">
                    <span v-if="getGenderBar('directed_to', label)" class="inline-flex items-center gap-0.5">
                      <span class="text-blue-600 font-semibold">{{ getGenderBar('directed_to', label).m }}</span>
                      <span class="text-gray-300">/</span>
                      <span class="text-slate-800 font-semibold">{{ getGenderBar('directed_to', label).f }}</span>
                    </span>
                    <span v-else class="text-gray-300">—</span>
                  </td>
                  <td class="py-1.5 text-right font-bold text-slate-800">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Customer Age Distribution — horizontal bar chart -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Customer Age Distribution</div>
          <div v-if="Object.keys(ageGroups).length" class="space-y-2">
            <div v-for="(label, idx) in ['Under 18', '18-29', '30-49', '50-64', 'Over 65']" :key="label" class="flex items-center gap-3">
              <span class="text-xs text-gray-600 w-14 text-right font-medium">{{ label }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-lg overflow-hidden relative">
                <div class="h-full rounded-lg transition-all duration-500 bg-blue-600"
                  :style="{ width: ((ageGroups[label] || 0) / ageGroupMax * 100) + '%' }">
                </div>
              </div>
              <span class="text-xs text-gray-500 w-6 text-right font-semibold">{{ ageGroups[label] || 0 }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Gender Ratio -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Customer Gender Ratio</div>
          <div v-if="genderTotal > 0" class="space-y-4">
            <div class="w-full h-8 rounded-lg overflow-hidden flex">
              <div class="h-full bg-blue-600 transition-all duration-500 flex items-center justify-center"
                :style="{ width: ((genderCounts.Male || 0) / genderTotal * 100) + '%' }">
                <span v-if="(genderCounts.Male || 0) / genderTotal > 0.15" class="text-xs font-bold text-white">{{ genderCounts.Male || 0 }}</span>
              </div>
              <div class="h-full bg-slate-800 transition-all duration-500 flex items-center justify-center"
                :style="{ width: ((genderCounts.Female || 0) / genderTotal * 100) + '%' }">
                <span v-if="(genderCounts.Female || 0) / genderTotal > 0.15" class="text-xs font-bold text-white">{{ genderCounts.Female || 0 }}</span>
              </div>
            </div>
            <div class="flex items-center justify-center gap-6">
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-blue-600"></span>
                <span class="text-sm text-slate-700 font-medium">Male ({{ genderCounts.Male || 0 }})</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-slate-800"></span>
                <span class="text-sm text-slate-700 font-medium">Female ({{ genderCounts.Female || 0 }})</span>
              </div>
            </div>
            <div class="text-center text-lg font-bold text-gray-800">
              {{ genderCounts.Male || 0 }} : {{ genderCounts.Female || 0 }}
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">No gender data available</span>
        </div>

        <!-- Customer Coming From — horizontal bars -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 260px;">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Customer Coming From</div>
          <div v-if="Object.keys(customerComingFromCounts).length" class="space-y-2">
            <div v-for="(count, label) in customerComingFromCounts" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-gray-600 w-36 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
                <div class="h-full bg-blue-600 rounded-full transition-all duration-500"
                  :style="{ width: (count / customerComingFromMax * 100) + '%' }"></div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ count }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">No data available</span>
        </div>

        <!-- Q7a · Counselling Own Language — M/F breakdown -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 220px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q7a · Counselling in Own Language</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="genderBreakdown.counselling_own_language && Object.keys(genderBreakdown.counselling_own_language).length" class="space-y-3">
            <div v-for="(gd, label) in genderBreakdown.counselling_own_language" :key="label" class="flex items-center gap-3">
              <span class="text-xs text-gray-700 font-medium w-24 flex-shrink-0">{{ label }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden flex">
                <div class="h-full bg-blue-600 transition-all duration-500 flex items-center justify-center"
                  :style="{ width: (gd.Male / Math.max(1, gd.Male + gd.Female + gd.Unknown) * 100) + '%' }">
                  <span v-if="gd.Male" class="text-[10px] text-white font-bold">{{ gd.Male }}</span>
                </div>
                <div class="h-full bg-slate-800 transition-all duration-500 flex items-center justify-center"
                  :style="{ width: (gd.Female / Math.max(1, gd.Male + gd.Female + gd.Unknown) * 100) + '%' }">
                  <span v-if="gd.Female" class="text-[10px] text-white font-bold">{{ gd.Female }}</span>
                </div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ gd.Male + gd.Female + gd.Unknown }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Q7b · Interpreter Present — M/F breakdown -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 220px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q7b · Interpreter Present</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="genderBreakdown.interpreter_present && Object.keys(genderBreakdown.interpreter_present).length" class="space-y-3 overflow-y-auto" style="max-height: 160px;">
            <div v-for="(gd, label) in genderBreakdown.interpreter_present" :key="label" class="flex items-center gap-3">
              <span class="text-xs text-gray-700 font-medium w-24 truncate flex-shrink-0" :title="label">{{ label }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden flex">
                <div class="h-full bg-blue-600 transition-all duration-500 flex items-center justify-center"
                  :style="{ width: (gd.Male / Math.max(1, gd.Male + gd.Female + gd.Unknown) * 100) + '%' }">
                  <span v-if="gd.Male" class="text-[10px] text-white font-bold">{{ gd.Male }}</span>
                </div>
                <div class="h-full bg-slate-800 transition-all duration-500 flex items-center justify-center"
                  :style="{ width: (gd.Female / Math.max(1, gd.Male + gd.Female + gd.Unknown) * 100) + '%' }">
                  <span v-if="gd.Female" class="text-[10px] text-white font-bold">{{ gd.Female }}</span>
                </div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ gd.Male + gd.Female + gd.Unknown }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Q17b · First Time Visitor — M/F breakdown -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200" style="height: 220px;">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">Q17b · First Time Visitor</div>
            <div class="flex items-center gap-2 text-[10px]"><span class="w-2.5 h-2.5 rounded-sm bg-blue-600"></span><span class="text-gray-500">M</span><span class="w-2.5 h-2.5 rounded-sm bg-slate-800"></span><span class="text-gray-500">F</span></div>
          </div>
          <div v-if="genderBreakdown.first_time_visitor && Object.keys(genderBreakdown.first_time_visitor).length" class="space-y-3">
            <div v-for="(gd, label) in genderBreakdown.first_time_visitor" :key="label" class="flex items-center gap-3">
              <span class="text-xs text-gray-700 font-medium w-24 flex-shrink-0">{{ label }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden flex">
                <div class="h-full bg-blue-600 transition-all duration-500 flex items-center justify-center"
                  :style="{ width: (gd.Male / Math.max(1, gd.Male + gd.Female + gd.Unknown) * 100) + '%' }">
                  <span v-if="gd.Male" class="text-[10px] text-white font-bold">{{ gd.Male }}</span>
                </div>
                <div class="h-full bg-slate-800 transition-all duration-500 flex items-center justify-center"
                  :style="{ width: (gd.Female / Math.max(1, gd.Male + gd.Female + gd.Unknown) * 100) + '%' }">
                  <span v-if="gd.Female" class="text-[10px] text-white font-bold">{{ gd.Female }}</span>
                </div>
              </div>
              <span class="text-xs font-bold text-slate-800 w-6 text-right flex-shrink-0">{{ gd.Male + gd.Female + gd.Unknown }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Combined Insights Tags (Q20 + Q22) -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200 md:col-span-2 xl:col-span-3">
          <div class="text-xs text-slate-500 uppercase tracking-wide mb-3">Insights · Additional Info & Feedback ({{ combinedInsightTags.length }} tags)</div>
          <div v-if="combinedInsightTags.length" class="flex flex-wrap gap-2 overflow-y-auto" style="max-height: 200px;">
            <span v-for="(v, i) in combinedInsightTags" :key="i" class="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-indigo-50 text-indigo-800 border border-indigo-200">
              {{ v }}
            </span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- FAQs Section -->
        <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-200 md:col-span-2 xl:col-span-3">
          <div class="flex items-center justify-between mb-3">
            <div class="text-xs text-slate-500 uppercase tracking-wide">FAQs · Common Customer Queries ({{ faqs.length }})</div>
            <button v-if="!faqs.length && totalForms > 0" @click="generateFaqs" :disabled="isGeneratingFaqs" class="text-xs px-3 py-1 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition">
              {{ isGeneratingFaqs ? 'Generating...' : 'Generate FAQs' }}
            </button>
            <button v-if="faqs.length" @click="generateFaqs" :disabled="isGeneratingFaqs" class="text-xs px-3 py-1 rounded-lg border border-gray-200 text-slate-600 hover:bg-gray-50 disabled:opacity-50 transition">
              {{ isGeneratingFaqs ? 'Regenerating...' : 'Regenerate' }}
            </button>
          </div>
          <div v-if="faqs.length" class="space-y-3 overflow-y-auto" style="max-height: 360px;">
            <details v-for="(faq, i) in faqs" :key="i" class="group border border-gray-100 rounded-lg">
              <summary class="flex items-center gap-2 px-4 py-3 cursor-pointer text-sm font-medium text-slate-800 hover:bg-gray-50 transition">
                <svg class="w-4 h-4 text-indigo-500 flex-shrink-0 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                {{ faq.question }}
              </summary>
              <div class="px-4 pb-3 pt-1 text-sm text-gray-600 border-t border-gray-50 ml-6">{{ faq.answer }}</div>
            </details>
          </div>
          <span v-else-if="!isGeneratingFaqs" class="text-gray-300 italic text-sm">Click "Generate FAQs" to create FAQ entries from submitted forms.</span>
        </div>

      </div>
    </div>


    <!-- ── CRM Forms Modal ── -->
    <div v-if="showCrmModal" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl">

        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 class="text-xl font-bold text-gray-900">Analyze Submitted CRM Forms</h2>
          <button @click="closeCrmModal" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
        </div>

        <!-- Body -->
        <div class="flex-1 overflow-y-auto px-6 py-4">
          <div v-if="isLoadingCrmForms" class="text-center py-16 text-gray-400">Loading...</div>
          <div v-else-if="crmForms.length === 0" class="text-center py-16 text-gray-400">No CRM forms found.</div>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm border-collapse">
              <thead>
                <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th class="px-3 py-3">
                    <input type="checkbox" @change="toggleCrmSelectAll"
                      :checked="crmSelectAllChecked" :indeterminate="crmSelectAllIndeterminate"
                      class="w-4 h-4 cursor-pointer" />
                  </th>
                  <th class="px-3 py-3">S.No.</th>
                  <th class="px-3 py-3">Username</th>
                  <th class="px-3 py-3">Audio File</th>
                  <th class="px-3 py-3">Date</th>
                  <th class="px-3 py-3">Time</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(form, i) in crmForms" :key="form.file_path"
                  class="border-b border-gray-100 hover:bg-blue-50 transition cursor-pointer"
                  @click="toggleCrmFormSelection(form.file_path)">
                  <td class="px-3 py-3">
                    <input type="checkbox"
                      :checked="selectedCrmPaths.has(form.file_path)"
                      @click.stop="toggleCrmFormSelection(form.file_path)"
                      class="w-4 h-4 cursor-pointer" />
                  </td>
                  <td class="px-3 py-3 text-gray-500">{{ i + 1 }}</td>
                  <td class="px-3 py-3 font-medium text-gray-800">{{ form.username }}</td>
                  <td class="px-3 py-3 text-gray-600">{{ form.audio_filename }}</td>
                  <td class="px-3 py-3 text-gray-600">{{ form.date }}</td>
                  <td class="px-3 py-3 text-gray-600">{{ form.time }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-2xl">
          <span class="text-sm text-gray-500">{{ selectedCrmPaths.size }} form(s) selected</span>
          <div class="flex gap-3">
            <button @click="closeCrmModal" class="px-4 py-2 rounded-xl border border-gray-300 text-gray-600 hover:bg-gray-100 text-sm transition">Cancel</button>
            <button @click="parseCrmForms" :disabled="selectedCrmPaths.size === 0"
              class="px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 text-sm transition">
              Analyze Selected
            </button>
          </div>
        </div>
      </div>
    </div>


    <!-- ── Floating AI Assistant ── -->
    <div class="fixed bottom-6 right-6 z-20">
      <div v-if="isMinimized"
        class="flex items-center gap-2 bg-white/90 backdrop-blur-md border border-white/30 rounded-full shadow-xl px-4 py-2 cursor-pointer hover:bg-white transition"
        @click="expandChat">
        <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/>
        </svg>
        <span class="text-sm font-medium text-gray-700">AI Assistant</span>
        <span v-if="unreadCount > 0" class="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
          {{ unreadCount > 9 ? '9+' : unreadCount }}
        </span>
      </div>
      <div v-else class="w-96 h-[500px] bg-white/95 backdrop-blur-md rounded-xl shadow-2xl border border-white/50 flex flex-col overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200/50 bg-gray-50">
          <h3 class="font-semibold text-gray-800 text-sm">Immigration Assistant</h3>
          <div class="flex gap-2">
            <button @click="clearConversation" class="text-gray-400 hover:text-gray-600">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
              </svg>
            </button>
            <button @click="isMinimized = true" class="text-gray-400 hover:text-gray-600">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
              </svg>
            </button>
          </div>
        </div>
        <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-3">
          <div v-for="(msg, idx) in messages" :key="idx" class="flex" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
            <div class="max-w-[80%] rounded-xl px-4 py-2 text-sm"
              :class="msg.role === 'user' ? 'bg-blue-600 text-white rounded-br-none' : 'bg-gray-100 text-gray-800 rounded-bl-none'">
              <p class="whitespace-pre-wrap">{{ msg.content }}</p>
              <span class="text-[10px] opacity-60 mt-1 block">{{ formatTime(msg.timestamp) }}</span>
            </div>
          </div>
          <div v-if="isTyping" class="flex justify-start">
            <div class="bg-gray-100 rounded-xl rounded-bl-none px-4 py-3">
              <div class="flex gap-1">
                <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay:150ms"></span>
                <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay:300ms"></span>
              </div>
            </div>
          </div>
        </div>
        <div class="border-t border-gray-200/50 p-3 bg-white/50">
          <div class="flex gap-2">
            <input v-model="newMessage" @keypress.enter="sendMessage" type="text"
              placeholder="Ask about applications..."
              class="flex-1 px-4 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :disabled="isTyping" />
            <button @click="sendMessage" :disabled="!newMessage.trim() || isTyping"
              class="p-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 transition disabled:opacity-40">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

  </div>
  `
};
