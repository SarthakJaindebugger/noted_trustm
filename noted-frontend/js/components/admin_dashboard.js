import { ref, nextTick, computed } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';

export default {
  name: 'AdminDashboard',

  setup() {
    const router = useRouter();
    const searchQuery = ref('');
    const applications = ref([
      {
        id: 'APP-2024-456',
        name: 'Maria Garcia',
        priority: 'High',
        status: 'Pending Review',
        type: 'Work Permit',
        officer: 'Officer Chen',
        submitted: 'April 2, 2026'
      },
      {
        id: 'APP-2024-457',
        name: 'Ahmed Hassan',
        priority: 'Medium',
        status: 'Documents Required',
        type: 'Family Reunification',
        officer: 'Officer Martinez',
        submitted: 'April 2, 2026'
      },
      {
        id: 'APP-2024-458',
        name: 'Sophie Laurent',
        priority: 'Low',
        status: 'In Review',
        type: 'Student Visa',
        officer: 'Officer Johnson',
        submitted: 'April 1, 2026'
      },
      {
        id: 'APP-2024-459',
        name: 'Yuki Tanaka',
        priority: 'Low',
        status: 'Approved',
        type: 'Tourist Visa',
        officer: 'Officer Smith',
        submitted: 'March 31, 2026'
      },
      {
        id: 'APP-2024-460',
        name: 'Carlos Rodriguez',
        priority: 'High',
        status: 'Interview Scheduled',
        type: 'Permanent Residency',
        officer: 'Officer Brown',
        submitted: 'March 30, 2026'
      }
    ]);

    // ----- Floating Chat State -----
    const messages = ref([
      {
        role: 'assistant',
        content: '👋 Hello! I\'m your AI immigration assistant. I can help you analyze applications, provide insights on the dashboard data, or answer questions about immigration processes. What would you like to know?',
        timestamp: Date.now()
      }
    ]);
    const newMessage = ref('');
    const isTyping = ref(false);
    const isMinimized = ref(false);
    const messagesContainer = ref(null);

    // For unread badge – increases while minimized and new assistant messages arrive
    let unreadCounter = 0;
    const unreadCount = ref(0);

    // Scroll helper
    const scrollToBottom = async () => {
      await nextTick();
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
      }
    };

    // Format time
    const formatTime = (timestamp) => {
      const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    // Mock LLM response – contextually uses dashboard data
    const generateMockResponse = async (userMessage) => {
      // Simulate network delay
      await new Promise(resolve => setTimeout(resolve, 800 + Math.random() * 700));

      const lowerMsg = userMessage.toLowerCase();
      const apps = applications.value;      // access the array inside the ref
      const totalApps = 1284;
      const pendingCount = 342;
      const highPriorityApps = apps.filter(app => app.priority === 'High').length;
      const pendingReviewApps = apps.filter(app => app.status === 'Pending Review').length;
      const recentAppsList = apps.slice(0, 3).map(app => app.name).join(', ');

      if (lowerMsg.includes('pending') || lowerMsg.includes('review')) {
        return `📋 There are currently ${pendingCount} applications pending review overall. Among the recent applications, ${pendingReviewApps} are marked as "Pending Review". The oldest pending from your list is ${apps.find(a => a.status === 'Pending Review')?.name || 'none'}. Would you like me to prioritize specific cases?`;
      }
      if (lowerMsg.includes('priority') || lowerMsg.includes('urgent')) {
        return `⚠️ High priority applications: ${highPriorityApps} out of ${apps.length} recent applications. Top priority cases: ${apps.filter(a => a.priority === 'High').map(a => a.name).join(', ')}. Consider reviewing ${apps.find(a => a.priority === 'High' && a.status !== 'Approved')?.name || 'Maria Garcia'} first.`;
      }
      if (lowerMsg.includes('work permit') || lowerMsg.includes('visa type')) {
        return `📊 Application breakdown by type: Work Permit (30%), Tourist Visa (22%), Student Visa (15%), Family Reunification (19%), Permanent Residency (14%). Would you like detailed stats on any specific type?`;
      }
      if (lowerMsg.includes('trend') || lowerMsg.includes('chart')) {
        return `📈 Application trends show +12.5% total volume vs last month. Pending cases decreased by 8.2%, while approvals today are up 23.1%. The growth in Work Permit applications is driving most of the increase.`;
      }
      if (lowerMsg.includes('officer') || lowerMsg.includes('assign')) {
        return `👩‍💼 Active officers: 24 total. Currently assigned officers include Officer Chen (Work Permit), Officer Martinez (Family), Officer Johnson (Student), Officer Smith (Tourist), Officer Brown (PR). Need to reassign a specific application?`;
      }
      if (lowerMsg.includes('maria') || lowerMsg.includes('garcia')) {
        return `👤 Maria Garcia - Application APP-2024-456, Work Permit, High Priority, Pending Review. Submitted April 2, 2026, assigned to Officer Chen. Would you like to take action on this application?`;
      }
      if (lowerMsg.includes('hello') || lowerMsg.includes('hi') || lowerMsg.includes('hey')) {
        return `Hello! I'm ready to assist with your immigration dashboard. You can ask me about pending applications, priorities, visa types, officer assignments, or any immigration policy. How can I help today?`;
      }
      if (lowerMsg.includes('help')) {
        return `Here are some things you can ask me:\n• "Show pending applications"\n• "What are high priority cases?"\n• "Application trends"\n• "Visa type breakdown"\n• "Info about Maria Garcia"\n• "Officer assignments"\nI'll provide insights based on your dashboard data.`;
      }

      // Default response
      return `🤖 I see you're asking about "${userMessage.substring(0, 50)}". As your AI assistant, I can help with:\n\n• Real-time application stats (${totalApps} total, ${pendingCount} pending)\n• Priority tracking (${highPriorityApps} high priority cases)\n• Recent applications: ${recentAppsList}\n\nFor deeper insights, try asking about specific applicants, visa types, or trends. Backend LLM integration will add even more powerful analysis soon!`;
    };

    // Send message and simulate LLM response
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
        const responseContent = await generateMockResponse(content);
        messages.value.push({
          role: 'assistant',
          content: responseContent,
          timestamp: Date.now()
        });
        // If chat is minimized, increase unread counter
        if (isMinimized.value) {
          unreadCounter++;
          unreadCount.value = unreadCounter;
        }
        await scrollToBottom();
      } catch (error) {
        messages.value.push({
          role: 'assistant',
          content: 'Sorry, I encountered an issue. Please try again later.',
          timestamp: Date.now()
        });
        await scrollToBottom();
      } finally {
        isTyping.value = false;
      }
    };

    // Clear conversation history
    const clearConversation = () => {
      messages.value = [
        {
          role: 'assistant',
          content: '✨ Conversation cleared. How can I assist you with your immigration dashboard today?',
          timestamp: Date.now()
        }
      ];
      unreadCounter = 0;
      unreadCount.value = 0;
      scrollToBottom();
    };

    // Expand chat – reset unread counter
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

    return {
      searchQuery,
      applications,
      logout,
      // Chat data
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
    };
  },

  template: `
    <div class="min-h-screen bg-gradient-to-br from-blue-50 via-white to-cyan-50">

      <!-- Header (unchanged) -->
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
        <!-- Stats row (same) -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Total Applications</div>
            <div class="text-4xl font-bold mt-2">1,284</div>
            <div class="text-green-600 mt-2">+12.5% vs last month</div>
          </div>
          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Pending Review</div>
            <div class="text-4xl font-bold mt-2">342</div>
            <div class="text-green-600 mt-2">-8.2% vs last month</div>
          </div>
          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Approved Today</div>
            <div class="text-4xl font-bold mt-2">89</div>
            <div class="text-green-600 mt-2">+23.1% vs last month</div>
          </div>
          <div class="glass-card p-6 rounded-2xl">
            <div class="text-gray-500">Active Officers</div>
            <div class="text-4xl font-bold mt-2">24</div>
            <div class="text-green-600 mt-2">+2 vs last month</div>
          </div>
        </div>

        <!-- Charts Row -->
        <div class="grid lg:grid-cols-2 gap-6">
          <div class="glass-card rounded-2xl p-6">
            <h2 class="text-xl font-semibold mb-4">Application Trends</h2>
            <div class="h-72 flex items-center justify-center text-gray-500">Monthly application chart placeholder</div>
          </div>
          <div class="glass-card rounded-2xl p-6">
            <h2 class="text-xl font-semibold mb-4">Applications by Type</h2>
            <div class="space-y-4">
              <div>Work Permit: 30%</div>
              <div>Tourist Visa: 22%</div>
              <div>Student Visa: 15%</div>
              <div>Family Reunification: 19%</div>
              <div>Permanent Residency: 14%</div>
            </div>
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

      <!-- Floating AI Assistant Widget -->
      <div class="fixed bottom-6 right-6 z-20">
        <!-- Minimized View -->
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

        <!-- Expanded Chat Window -->
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

          <!-- Messages -->
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

          <!-- Input Bar -->
          <div class="border-t border-gray-200/50 p-3 bg-white/50">
            <div class="flex items-center gap-2">
              <input v-model="newMessage" @keypress.enter="sendMessage" type="text" placeholder="Ask about applications, stats, or any immigration question..." class="flex-1 px-4 py-2 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" :disabled="isTyping" />
              <button @click="sendMessage" :disabled="!newMessage.trim() || isTyping" class="p-2 rounded-xl bg-blue-600 text-white disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700 transition">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
            <p class="text-xs text-gray-400 mt-2 text-center">✨ Backend integration coming soon — mock AI responses active</p>
          </div>
        </div>
      </div>
    </div>
  `
};