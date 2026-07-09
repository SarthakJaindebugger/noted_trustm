import { ref, nextTick, computed } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';

export default {
  name: 'AdminDashboard',

  setup() {
    const router = useRouter();
    const searchQuery = ref('');
    
    // ----- Replace with real data source -----
    const applications = ref([]);
    const totalApplications = ref(0);
    const pendingReview = ref(0);
    const approvedToday = ref(0);
    const activeOfficers = ref(0);
    const trendsData = ref({});
    const applicationTypes = ref([]);
    // New dashboard fields (placeholders — will be filled dynamically)
    const averageConversationTime = ref('—');
    const contactMethods = ref([]); // e.g. ['phone','email']
    const numberOfCustomers = ref('—');
    const genderRatio = ref('—');
    const ageGroups = ref([]); // e.g. [{range:'18-25', pct:20}, ...]
    const countryOfOrigin = ref([]); // e.g. [{country:'Finland', pct:70}]
    const durationResidence = ref([]); // e.g. [{range:'<1yr', pct:10}, ...]
    const topicsDiscussed = ref([]); // e.g. ['work visa','benefits']
    const purposesOfVisit = ref([]); // e.g. ['consultation','application']
    const customerFeedbacks = ref([]); // e.g. [{text:'Great service', rating:5}]

    // ----- Floating Chat State -----
    const messages = ref([
      {
        role: 'assistant',
        content: '👋 Hello! I\'m your AI immigration assistant. I can answer questions based on official immigration documents and policies. What would you like to know?',
        timestamp: Date.now()
      }
    ]);
    const newMessage = ref('');
    const isTyping = ref(false);
    const isMinimized = ref(false);
    const messagesContainer = ref(null);
    let unreadCounter = 0;
    const unreadCount = ref(0);

    const scrollToBottom = async () => {
      await nextTick();
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
      }
    };

    const formatTime = (timestamp) => {
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    // ----- REAL RAG API CALL -----
    const getRAGResponse = async (userQuery) => {
      const token = authService.getToken();
      const apiUrl = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://127.0.0.1:8000/api/v1/rag/query'
        : '/api/rag/query';

      console.debug('Calling RAG API', { apiUrl, tokenPresent: !!token, query: userQuery });

      try {
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          },
          body: JSON.stringify({
            query: userQuery,
            top_k: 5   // you can adjust
          })
        });

        if (!response.ok) {
          const errorText = await response.text();
          console.error('RAG API error response:', {
            status: response.status,
            statusText: response.statusText,
            body: errorText,
          });
          throw new Error(`RAG API error: ${response.status}`);
        }

        const data = await response.json();
        return data.response;   // backend returns { response, context_docs }
      } catch (error) {
        console.error('RAG API call failed:', error);
        return 'Sorry, I could not retrieve information from the knowledge base. Please try again later.';
      }
    };

    // Updated sendMessage – uses real RAG
    const sendMessage = async () => {
      const content = newMessage.value.trim();
      if (!content || isTyping.value) return;

      // Add user message
      messages.value.push({
        role: 'user',
        content: content,
        timestamp: Date.now()
      });
      newMessage.value = '';
      await scrollToBottom();

      isTyping.value = true;
      try {
        const responseContent = await getRAGResponse(content);
        messages.value.push({
          role: 'assistant',
          content: responseContent,
          timestamp: Date.now()
        });
        if (isMinimized.value) {
          unreadCounter++;
          unreadCount.value = unreadCounter;
        }
        await scrollToBottom();
      } catch (error) {
        messages.value.push({
          role: 'assistant',
          content: 'An unexpected error occurred. Please try again later.',
          timestamp: Date.now()
        });
        await scrollToBottom();
      } finally {
        isTyping.value = false;
      }
    };

    const clearConversation = () => {
      messages.value = [
        {
          role: 'assistant',
          content: '✨ Conversation cleared. How can I assist you with immigration questions today?',
          timestamp: Date.now()
        }
      ];
      unreadCounter = 0;
      unreadCount.value = 0;
      scrollToBottom();
    };

    const expandChat = () => {
      isMinimized.value = false;
      unreadCounter = 0;
      unreadCount.value = 0;
      scrollToBottom();
    };

    const logout = async () => {
      authService.logout();
      localStorage.removeItem('isAdmin');
      router.push({ name: 'login' });
    };

    // Uncomment and adapt when you have a real dashboard API
    const fetchDashboardData = async () => {
      const token = authService.getToken();
      const apiUrl = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://127.0.0.1:8000/api/v1/admin/stats'
        : '/api/v1/admin/stats';

      try {
        const resp = await fetch(apiUrl, {
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          }
        });
        if (!resp.ok) {
          console.error('Failed to load admin stats', resp.status);
          return;
        }
        const data = await resp.json();
        averageConversationTime.value = data.average_conversation_time || '—';
        contactMethods.value = data.contact_methods || [];
        numberOfCustomers.value = data.number_of_customers || '—';
        genderRatio.value = data.gender_ratio || '—';
        // Age groups: expect [{range, count, pct}]
        ageGroups.value = data.age_groups || [];
        countryOfOrigin.value = data.country_of_origin || [];
        durationResidence.value = data.duration_of_residence || [];
        // Clean topics: remove unspecified/none entries and normalize whitespace
        const rawTopics = data.topics_discussed || [];
        const cleaned = rawTopics
          .map((t) => {
            if (!t) return null;
            const topic = (t.topic || t).toString();
            let s = topic.replace(/The topics discussed in this visit are:\s*/i, '');
            s = s.replace(/\n+/g, ' ').replace(/\s+/g, ' ').trim();
            s = s.replace(/[\.|,;]$/g, '');
            return { topic: s, pct: t.pct ?? null, count: t.count ?? null };
          })
          .filter((t) => t && t.topic && !/not specified|none|n\/a|not available/i.test(t.topic));
        topicsDiscussed.value = cleaned;
        purposesOfVisit.value = data.purposes_of_visit || [];
        customerFeedbacks.value = data.customer_feedbacks || [];
      } catch (err) {
        console.error('Error fetching dashboard data', err);
      }
    };
    // load on setup
    fetchDashboardData();

    return {
      searchQuery,
      applications,
      totalApplications,
      pendingReview,
      approvedToday,
      activeOfficers,
      applicationTypes,
      logout,
      messages,
      newMessage,
      isTyping,
      isMinimized,
      unreadCount,
      messagesContainer,
      sendMessage,
      clearConversation,
      formatTime,
      expandChat
      ,
      // new dashboard fields
      averageConversationTime,
      contactMethods,
      numberOfCustomers,
      genderRatio,
      ageGroups,
      countryOfOrigin,
      durationResidence,
      topicsDiscussed,
      purposesOfVisit,
      customerFeedbacks
    };
  },

   template: `
    <div class="min-h-screen bg-gradient-to-br from-blue-50 via-white to-cyan-50">
      <!-- Header -->
      <div class="sticky top-0 z-10 backdrop-blur-md bg-white/60 border-b border-white/30">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 class="text-3xl font-bold text-blue-900">Admin Dashboard</h1>
            <p class="text-gray-600">Comprehensive overview of immigration operations</p>
          </div>
          <button @click="logout" class="px-5 py-2 rounded-xl bg-red-500 text-white hover:bg-red-600 transition">Logout</button>
        </div>
      </div>

      <div class="max-w-7xl mx-auto p-6 space-y-8">
        <!-- New dashboard fields -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Average Conversation Time</div>
            <div class="text-2xl font-bold mt-2">{{ averageConversationTime }}</div>
          </div>

          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Contact Methods Used</div>
            <div class="text-lg mt-2" v-if="contactMethods.length">{{ contactMethods.join(', ') }}</div>
            <div class="text-gray-400 italic" v-else>—</div>
          </div>

          <div class="glass-card p-6 rounded-2xl h-64">
            <div class="text-gray-500">Number of Customers</div>
            <div class="text-2xl font-bold mt-2">{{ numberOfCustomers }}</div>
          </div>

          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Gender Ratio</div>
            <div class="text-lg mt-2">{{ genderRatio }}</div>
          </div>

          <div class="glass-card p-6 rounded-2xl h-80">
            <div class="flex justify-between items-center mb-4">
              <h3 class="font-semibold text-gray-800">Age Groups</h3>
              <span class="text-xs text-gray-500">{{ ageGroups.length }} groups</span>
            </div>

            <div v-if="ageGroups.length" class="space-y-4 overflow-y-auto h-[220px]">
              <div v-for="g in ageGroups" :key="g.range">
                <div class="flex justify-between text-sm mb-1">
                  <span class="font-medium text-gray-700">{{ g.range }}</span>
                  <span class="text-gray-500">{{ g.pct }}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2">
                  <div class="bg-green-500 h-2 rounded-full transition-all duration-500" :style="{ width: g.pct + '%' }"></div>
                </div>
              </div>
            </div>

            <div v-else class="h-[220px] flex items-center justify-center text-gray-400">—</div>
          </div>

          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Countries of Origin</div>
            <div class="text-sm mt-2" v-if="countryOfOrigin.length">
              <div v-for="c in countryOfOrigin" :key="c.country">{{ c.country }}: {{ c.pct }}%</div>
            </div>
            <div class="text-gray-400 italic" v-else>—</div>
          </div>

          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Duration of Residence</div>
            <div class="text-sm mt-2" v-if="durationResidence.length">
              <div v-for="d in durationResidence" :key="d.range">{{ d.range }}: {{ d.pct }}%</div>
            </div>
            <div class="text-gray-400 italic" v-else>—</div>
          </div>







          <div class="glass-card p-6 rounded-2xl h-80">
            <div class="flex justify-between items-center mb-4">
              <h3 class="font-semibold text-gray-800">
                Topics Discussed
              </h3>
              <span class="text-xs text-gray-500">
                {{ topicsDiscussed.length }} Topics
              </span>
            </div>

            <div
              v-if="topicsDiscussed.length"
              class="space-y-4 overflow-y-auto h-[220px]"
            >
              <div
                v-for="item in topicsDiscussed"
                :key="item.topic"
              >
                <div class="flex justify-between text-sm mb-1">
                  <span class="font-medium text-gray-700">
                    {{ item.topic }}
                  </span>

                  <span class="text-gray-500">
                    {{ item.pct }}%
                  </span>
                </div>

                <div class="w-full bg-gray-200 rounded-full h-2">
                  <div
                    class="bg-blue-600 h-2 rounded-full transition-all duration-500"
                    :style="{ width: item.pct + '%' }"
                  ></div>
                </div>
              </div>
            </div>

            <div
              v-else
              class="h-[220px] flex items-center justify-center text-gray-400"
            >
              No topics available
            </div>
          </div>









          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Purposes of Visit</div>
            <div class="text-sm mt-2" v-if="purposesOfVisit.length">{{ purposesOfVisit.join(', ') }}</div>
            <div class="text-gray-400 italic" v-else>—</div>
          </div>

          <div class="glass-card p-6 rounded-2xl col-span-1 lg:col-span-4">
            <div class="text-gray-500">Customer Feedbacks</div>
            <div class="mt-3 space-y-2" v-if="customerFeedbacks.length">
              <div v-for="(f, idx) in customerFeedbacks" :key="idx" class="bg-white/60 p-3 rounded-lg">
                <div class="text-gray-800">{{ f.text }}</div>
                <div class="text-xs text-gray-500">Rating: {{ f.rating || '—' }}</div>
              </div>
            </div>
            <div class="text-gray-400 italic" v-else>No feedbacks yet</div>
          </div>
        </div>

        <!-- Charts Row (placeholders – will be filled with real data) -->
        <div class="grid lg:grid-cols-2 gap-6">
          <div class="glass-card rounded-2xl p-6">
            <h2 class="text-xl font-semibold mb-4">Application Trends</h2>
            <div class="h-72 flex items-center justify-center text-gray-500">Chart placeholder – connect your charting library</div>
          </div>
          <div class="glass-card rounded-2xl p-6">
            <h2 class="text-xl font-semibold mb-4">Applications by Type</h2>
            <div v-if="applicationTypes.length" class="space-y-4">
              <div v-for="type in applicationTypes" :key="type.name">{{ type.name }}: {{ type.percentage }}%</div>
            </div>
            <div v-else class="text-gray-500 italic">No type data loaded</div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="glass-card rounded-2xl p-4">
          <div class="flex gap-6">
            <button class="font-semibold text-blue-600">Applications</button>
            <button>Officers</button>
            <button>Performance</button>
            <button>Schedule</button>
          </div>
        </div>

        <!-- Applications Table -->
        <div class="glass-card rounded-2xl p-6">
          <div class="flex justify-between items-center mb-6">
            <div>
              <h2 class="text-2xl font-semibold">Recent Applications</h2>
              <p class="text-gray-500">All applications requiring attention</p>
            </div>
            <input v-model="searchQuery" placeholder="Search applications..." class="px-4 py-2 rounded-xl border border-gray-200 w-72" />
          </div>
          <div class="space-y-4">
            <div v-if="applications.length === 0" class="text-center py-12 text-gray-500">
              No applications loaded. Please connect your data source.
            </div>
            <div v-for="app in applications" :key="app.id" class="bg-white/50 backdrop-blur-md border border-white/30 rounded-2xl p-5">
              <div class="flex justify-between items-start">
                <div>
                  <div class="flex items-center gap-3">
                    <h3 class="font-semibold text-lg">{{ app.name }}</h3>
                    <span class="px-3 py-1 rounded-full text-xs bg-red-100 text-red-700">{{ app.priority }}</span>
                    <span class="px-3 py-1 rounded-full text-xs bg-blue-100 text-blue-700">{{ app.status }}</span>
                  </div>
                  <div class="mt-3 text-gray-600">ID: {{ app.id }}</div>
                  <div class="text-gray-600">Type: {{ app.type }}</div>
                  <div class="text-gray-600">Officer: {{ app.officer }}</div>
                  <div class="text-gray-600">Submitted: {{ app.submitted }}</div>
                </div>
                <div class="flex gap-3">
                  <button class="px-4 py-2 rounded-xl bg-blue-500 text-white">Review</button>
                  <button class="px-4 py-2 rounded-xl bg-gray-200">Assign</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Floating AI Assistant Widget (unchanged, but mock responses no longer rely on hardcoded data) -->
      <div class="fixed bottom-6 right-6 z-20">
        <div v-if="isMinimized" class="flex items-center gap-2 bg-white/90 backdrop-blur-md border border-white/30 rounded-full shadow-xl px-4 py-2 cursor-pointer hover:bg-white transition" @click="expandChat">
          <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span class="text-sm font-medium text-gray-700">AI Assistant</span>
          <span v-if="unreadCount > 0" class="bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[20px] text-center">{{ unreadCount > 9 ? '9+' : unreadCount }}</span>
          <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
        <div v-else class="w-96 h-[500px] bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl border border-white/50 flex flex-col overflow-hidden transition-all duration-200">
          <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200/50 bg-gradient-to-r from-blue-50 to-cyan-50">
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <h3 class="font-semibold text-gray-800">Immigration Assistant</h3>
              <span class="text-xs text-gray-500">LLM Powered</span>
            </div>
            <div class="flex items-center gap-2">
              <button @click="clearConversation" class="text-gray-400 hover:text-gray-600 transition" title="Clear conversation">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
              <button @click="isMinimized = true" class="text-gray-400 hover:text-gray-600 transition">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
          </div>
          <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-3">
            <div v-for="(msg, idx) in messages" :key="idx" class="flex" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
              <div class="max-w-[80%] rounded-2xl px-4 py-2" :class="msg.role === 'user' ? 'bg-blue-600 text-white rounded-br-none' : 'bg-gray-100 text-gray-800 rounded-bl-none'">
                <p class="text-sm whitespace-pre-wrap">{{ msg.content }}</p>
                <span class="text-[10px] opacity-70 mt-1 block">{{ formatTime(msg.timestamp) }}</span>
              </div>
            </div>
            <div v-if="isTyping" class="flex justify-start">
              <div class="bg-gray-100 rounded-2xl rounded-bl-none px-4 py-2">
                <div class="flex gap-1">
                  <span class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                  <span class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                  <span class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
                </div>
              </div>
            </div>
          </div>
          <div class="border-t border-gray-200/50 p-3 bg-white/50">
            <div class="flex items-center gap-2">
              <input v-model="newMessage" @keypress.enter="sendMessage" type="text" placeholder="Ask about applications, stats, or any immigration question..." class="flex-1 px-4 py-2 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" :disabled="isTyping" />
              <button @click="sendMessage" :disabled="!newMessage.trim() || isTyping" class="p-2 rounded-xl bg-blue-600 text-white disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700 transition">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
            <p class="text-xs text-gray-400 mt-2 text-center">Data source not yet connected – add API call in setup()</p>
          </div>
        </div>
      </div>
    </div>
  `



};