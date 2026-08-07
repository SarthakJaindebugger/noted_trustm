import { ref, nextTick, computed, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { apiClient } from '../services/api_client.js';

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
    const otherFeedback     = ref([]);
    const ageGroups         = ref({});
    const genderCounts      = ref({});

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
        otherFeedback.value      = d.other_feedback     || [];
        ageGroups.value          = d.age_groups         || {};
        genderCounts.value       = d.gender_counts      || {};
      } catch (err) { console.error('Error fetching aggregated CRM data', err); }
    };

    fetchAggregatedCrmData();

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
        otherFeedback.value      = d.other_feedback     || [];
        ageGroups.value          = d.age_groups         || {};
        genderCounts.value       = d.gender_counts      || {};
        closeCrmModal();
      } catch (err) { console.error('Failed to parse CRM forms', err); alert('Failed to parse CRM forms.'); }
    };


    const ageGroupMax = computed(() => Math.max(1, ...Object.values(ageGroups.value || {})));
    const genderTotal = computed(() => (genderCounts.value.Male || 0) + (genderCounts.value.Female || 0));

    return {
      logout, totalForms, numberOfCustomers, averageConvTime,
      contactMethods, topicsDiscussed, purposesOfVisit, labourPositions,
      birthCountries, languages, residences, durationResidence,
      directedTo, heardFrom, immigrationReasons, educationLevels,
      additionalInfoTags, otherFeedback, ageGroups, ageGroupMax,
      genderCounts, genderTotal,
      showCrmModal, crmForms, selectedCrmPaths, isLoadingCrmForms,
      crmSelectAllChecked, crmSelectAllIndeterminate,
      openCrmModal, closeCrmModal, toggleCrmFormSelection, toggleCrmSelectAll, parseCrmForms,
      messages, newMessage, isTyping, isMinimized, unreadCount, messagesContainer,
      sendMessage, clearConversation, formatTime, expandChat,
    };
  },

  template: `
  <div class="min-h-screen bg-gradient-to-br from-blue-50 via-white to-cyan-50">

    <!-- ── Header ── -->
    <div class="sticky top-0 z-10 backdrop-blur-md bg-white/70 border-b border-white/30">
      <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold text-blue-900">Admin Dashboard</h1>
          <p class="text-gray-500 text-sm">Aggregated from {{ totalForms }} submitted CRM form(s)</p>
        </div>
        <div class="flex gap-3">
          <button @click="openCrmModal" class="px-5 py-2 rounded-xl bg-purple-600 text-white hover:bg-purple-700 transition text-sm font-medium">
            Analyze CRM Forms
          </button>
          <button @click="logout" class="px-5 py-2 rounded-xl bg-red-500 text-white hover:bg-red-600 transition text-sm font-medium">Logout</button>
        </div>
      </div>
    </div>

    <!-- ── Dashboard grid ── -->
    <div class="max-w-7xl mx-auto p-6 space-y-6">

      <!-- Summary row -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-1">Total Forms</div>
          <div class="text-3xl font-bold text-blue-700">{{ totalForms }}</div>
        </div>
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-1">Customers</div>
          <div class="text-3xl font-bold text-blue-700">{{ numberOfCustomers }}</div>
        </div>
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-1">Avg. Conv. Time</div>
          <div class="text-xl font-semibold text-gray-700 mt-1">{{ averageConvTime }}</div>
        </div>
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-1">Languages Detected</div>
          <div class="text-3xl font-bold text-blue-700">{{ languages.length }}</div>
        </div>
      </div>


      <!-- Full questionnaire fields grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">

        <!-- Contact Method -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q5 · Contact Method</div>
          <div v-if="contactMethods.length" class="flex flex-wrap gap-2">
            <span v-for="v in contactMethods" :key="v" class="px-2 py-1 bg-blue-50 text-blue-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Heard From -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q6 · Heard From</div>
          <div v-if="heardFrom.length" class="flex flex-wrap gap-2">
            <span v-for="v in heardFrom" :key="v" class="px-2 py-1 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Immigration Reason -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q10 · Reason for Immigration</div>
          <div v-if="immigrationReasons.length" class="flex flex-wrap gap-2">
            <span v-for="v in immigrationReasons" :key="v" class="px-2 py-1 bg-yellow-50 text-yellow-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Additional Info Tags -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q11 · Additional Customer Info</div>
          <div v-if="additionalInfoTags.length" class="flex flex-wrap gap-2">
            <span v-for="v in additionalInfoTags" :key="v" class="px-2 py-1 bg-orange-50 text-orange-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Birth Country -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q12 · Birth Country</div>
          <div v-if="birthCountries.length" class="flex flex-wrap gap-2">
            <span v-for="v in birthCountries" :key="v" class="px-2 py-1 bg-green-50 text-green-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Mother Tongue -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q13 · Mother Tongue / Language</div>
          <div v-if="languages.length" class="flex flex-wrap gap-2">
            <span v-for="v in languages" :key="v" class="px-2 py-1 bg-teal-50 text-teal-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>


        <!-- Education Level -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q14 · Education Level</div>
          <div v-if="educationLevels.length" class="flex flex-wrap gap-2">
            <span v-for="v in educationLevels" :key="v" class="px-2 py-1 bg-purple-50 text-purple-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Labour Position -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q15 · Position in Labour Market</div>
          <div v-if="labourPositions.length" class="flex flex-wrap gap-2">
            <span v-for="v in labourPositions" :key="v" class="px-2 py-1 bg-pink-50 text-pink-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Domicile -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q16 · Customer Domicile</div>
          <div v-if="residences.length" class="flex flex-wrap gap-2">
            <span v-for="v in residences" :key="v" class="px-2 py-1 bg-cyan-50 text-cyan-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Duration of Residence -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q17 · Duration of Residence in Finland</div>
          <div v-if="durationResidence.length" class="flex flex-wrap gap-2">
            <span v-for="v in durationResidence" :key="v" class="px-2 py-1 bg-sky-50 text-sky-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Contents of Visit -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 md:col-span-2 xl:col-span-1">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q18 · Contents of Customer Visit</div>
          <div v-if="topicsDiscussed.length" class="flex flex-wrap gap-2">
            <span v-for="v in topicsDiscussed" :key="v" class="px-2 py-1 bg-blue-50 text-blue-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Purpose of Visit -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q19 · Purpose of Visit</div>
          <div v-if="purposesOfVisit.length" class="flex flex-wrap gap-2">
            <span v-for="v in purposesOfVisit" :key="v" class="px-2 py-1 bg-violet-50 text-violet-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Where Directed -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q21 · Where Customer Is Directed</div>
          <div v-if="directedTo.length" class="flex flex-wrap gap-2">
            <span v-for="v in directedTo" :key="v" class="px-2 py-1 bg-lime-50 text-lime-700 rounded-lg text-xs font-medium">{{ v }}</span>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Customer Age Distribution — horizontal bar chart -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 md:col-span-2 xl:col-span-1">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Customer Age Distribution</div>
          <div v-if="Object.keys(ageGroups).length" class="space-y-2">
            <div v-for="(label, idx) in ['0-10', '10-20', '20-30', '30-50', '50+']" :key="label" class="flex items-center gap-3">
              <span class="text-xs text-gray-600 w-10 text-right font-medium">{{ label }}</span>
              <div class="flex-1 h-6 bg-gray-100 rounded-lg overflow-hidden relative">
                <div class="h-full rounded-lg transition-all duration-500"
                  :style="{ width: ((ageGroups[label] || 0) / ageGroupMax * 100) + '%' }"
                  :class="['bg-blue-500', 'bg-cyan-500', 'bg-teal-500', 'bg-indigo-500', 'bg-purple-500'][idx]">
                </div>
              </div>
              <span class="text-xs text-gray-500 w-6 text-right font-semibold">{{ ageGroups[label] || 0 }}</span>
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

        <!-- Gender Ratio -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Customer Gender Ratio</div>
          <div v-if="genderTotal > 0" class="space-y-4">
            <!-- Ratio bar -->
            <div class="w-full h-8 rounded-xl overflow-hidden flex">
              <div class="h-full bg-blue-500 transition-all duration-500 flex items-center justify-center"
                :style="{ width: ((genderCounts.Male || 0) / genderTotal * 100) + '%' }">
                <span v-if="(genderCounts.Male || 0) / genderTotal > 0.15" class="text-xs font-bold text-white">{{ genderCounts.Male || 0 }}</span>
              </div>
              <div class="h-full bg-pink-500 transition-all duration-500 flex items-center justify-center"
                :style="{ width: ((genderCounts.Female || 0) / genderTotal * 100) + '%' }">
                <span v-if="(genderCounts.Female || 0) / genderTotal > 0.15" class="text-xs font-bold text-white">{{ genderCounts.Female || 0 }}</span>
              </div>
            </div>
            <!-- Legend -->
            <div class="flex items-center justify-center gap-6">
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-blue-500"></span>
                <span class="text-sm text-gray-700 font-medium">Male ({{ genderCounts.Male || 0 }})</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-pink-500"></span>
                <span class="text-sm text-gray-700 font-medium">Female ({{ genderCounts.Female || 0 }})</span>
              </div>
            </div>
            <!-- Ratio text -->
            <div class="text-center text-lg font-bold text-gray-800">
              {{ genderCounts.Male || 0 }} : {{ genderCounts.Female || 0 }}
            </div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">No gender data available</span>
        </div>

        <!-- Other Feedback — full width -->
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 md:col-span-2 xl:col-span-3">
          <div class="text-xs text-gray-400 uppercase tracking-wide mb-3">Q22 · Other Feedback</div>
          <div v-if="otherFeedback.length" class="space-y-2">
            <div v-for="(v, i) in otherFeedback" :key="i" class="text-sm text-gray-700 bg-gray-50 rounded-xl px-4 py-3 leading-relaxed">{{ v }}</div>
          </div>
          <span v-else class="text-gray-300 italic text-sm">—</span>
        </div>

      </div>
    </div>


    <!-- ── CRM Forms Modal ── -->
    <div v-if="showCrmModal" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl">

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
                  class="border-b border-gray-100 hover:bg-purple-50 transition cursor-pointer"
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
              class="px-4 py-2 rounded-xl bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-40 text-sm transition">
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
      <div v-else class="w-96 h-[500px] bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl border border-white/50 flex flex-col overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200/50 bg-gradient-to-r from-blue-50 to-cyan-50">
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
            <div class="max-w-[80%] rounded-2xl px-4 py-2 text-sm"
              :class="msg.role === 'user' ? 'bg-blue-600 text-white rounded-br-none' : 'bg-gray-100 text-gray-800 rounded-bl-none'">
              <p class="whitespace-pre-wrap">{{ msg.content }}</p>
              <span class="text-[10px] opacity-60 mt-1 block">{{ formatTime(msg.timestamp) }}</span>
            </div>
          </div>
          <div v-if="isTyping" class="flex justify-start">
            <div class="bg-gray-100 rounded-2xl rounded-bl-none px-4 py-3">
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
