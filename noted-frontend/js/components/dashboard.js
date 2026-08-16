import { ref, computed, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { sessionService } from '../services/session_service.js';
import { apiClient } from '../services/api_client.js';
import { languageService } from '../services/language_service.js';

export default {
    name: 'Dashboard',
    setup() {
        const router = useRouter();
        const fileInput = ref(null);
        const isUploading = ref(false);
        const uploadProgress = ref(0);
        const message = ref('');
        const error = ref('');

        // ----- Analyze Audio State -----
        const completedAudioFiles = ref([]);
        const newAudioFiles = ref([]);
        const audioFiles = ref([]);
        const selectedPaths = reactive(new Set()); // Multi-select: audio paths (only from newAudioFiles)
        const processingQueue = ref([]); // Queue of paths to process
        const currentProcessingPath = ref(null); // Currently processing audio
        const processingProgress = ref(null); // { path, percent, status }
        const analysisResults = reactive({}); // { path: result }
        const crmFormStatusCache = reactive({}); // { filename: exists }
        const submittedAudioFiles = ref(new Set());

        // Computed helpers
        const isAnalyzing = computed(() => processingQueue.value.length > 0 || currentProcessingPath.value !== null);

        const selectAllChecked = computed(() => {
            return newAudioFiles.value.length > 0 && newAudioFiles.value.every(af => selectedPaths.has(af.path));
        });

        const selectAllIndeterminate = computed(() => {
            return selectedPaths.size > 0 && !selectAllChecked.value;
        });

        // Parse date/time from audio file path or use file modification time
        const parseAudioFileInfo = (audioFile) => {
            const name = audioFile.display_name || audioFile.name;
            // Try to extract date from path, fallback to current date
            const date = new Date().toLocaleDateString('de-DE'); // DD.MM.YYYY
            const time = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return { name, date, time };
        };

        const toggleAudioSelection = (audioPath) => {
            if (selectedPaths.has(audioPath)) {
                selectedPaths.delete(audioPath);
            } else {
                selectedPaths.add(audioPath);
            }
        };

        const toggleSelectAll = () => {
            if (selectAllChecked.value) {
                selectedPaths.clear();
            } else {
                newAudioFiles.value.forEach(af => selectedPaths.add(af.path));
            }
        };

        const chooseAudio = () => {
            fileInput.value?.click();
        };

        const logout = async () => {
            authService.logout();
            await router.push({ name: 'login' });
        };

        const uploadAudio = async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;

            isUploading.value = true;
            uploadProgress.value = 0;
            message.value = '';
            error.value = '';

            try {
                const result = await sessionService.uploadUserAudio(file, (progress) => {
                    uploadProgress.value = progress;
                });
                uploadProgress.value = 100;
                message.value = result.message || 'Uploaded successfully.';
                await loadAudioFiles();
            } catch (uploadError) {
                error.value = uploadError.message || 'Unable to upload the audio file.';
            } finally {
                isUploading.value = false;
                event.target.value = '';
            }
        };

        const loadAudioFiles = async () => {
            try {
                const data = await apiClient.get('/audio/analyze-files-categorized');
                completedAudioFiles.value = (data.completed || []).sort((a, b) => a.name.localeCompare(b.name));
                newAudioFiles.value = (data.new || []).sort((a, b) => a.name.localeCompare(b.name));
                audioFiles.value = [...completedAudioFiles.value, ...newAudioFiles.value];
                selectedPaths.clear();
                await loadSubmissionStatuses();
            } catch (loadError) {
                console.error('Failed to load audio files', loadError);
                error.value = loadError.message || 'Failed to load audio files.';
            }
        };

        const loadSubmissionStatuses = async () => {
            try {
                const resp = await apiClient.get('/audio/crm-form-submissions');
                submittedAudioFiles.value = new Set(resp.submitted_audio_files || []);
            } catch (err) {
                console.error('Failed to load submission statuses', err);
            }
        };

        const isSubmitted = (audioFile) => {
            return submittedAudioFiles.value.has(audioFile.name);
        };

        const checkCrmFormStatus = async (audioFilename) => {
            try {
                const response = await apiClient.get(`/audio/crm-form-status?audio_filename=${encodeURIComponent(audioFilename)}`);
                crmFormStatusCache[audioFilename] = response.crm_form_exists || false;
            } catch (err) {
                console.error('Failed to check CRM form status', err);
                crmFormStatusCache[audioFilename] = false;
            }
        };

        const isCrmFormAvailable = (audioFile) => {
            // CRM is available if: analysis is complete (in results) OR form already exists
            const hasAnalysis = analysisResults[audioFile.path];
            const formExists = crmFormStatusCache[audioFile.name];
            return hasAnalysis || formExists;
        };

        const startBatchAnalysis = async () => {
            if (selectedPaths.size === 0) {
                error.value = 'Please select at least one audio file.';
                return;
            }

            // Sort selected paths alphabetically and queue them
            processingQueue.value = Array.from(selectedPaths).sort();
            selectedPaths.clear();
            error.value = '';
            message.value = '';
            
            // Process queue sequentially
            await processQueueSequentially();
        };

        const processQueueSequentially = async () => {
            while (processingQueue.value.length > 0) {
                const audioPath = processingQueue.value.shift();
                currentProcessingPath.value = audioPath;
                processingProgress.value = { path: audioPath, percent: 0, status: 'Starting analysis...' };

                try {
                    processingProgress.value.status = 'Analyzing audio...';
                    processingProgress.value.percent = 50;

                    const result = await apiClient.post('/audio/analyze', { audio_path: audioPath });
                    analysisResults[audioPath] = result;

                    processingProgress.value.percent = 100;
                    processingProgress.value.status = 'Analysis complete';
                    
                    // Check if CRM form now exists
                    const audioFile = audioFiles.value.find(af => af.path === audioPath);
                    if (audioFile) {
                        await checkCrmFormStatus(audioFile.name);
                    }

                    // Wait briefly before next analysis
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (analyzeError) {
                    console.error('Audio analysis failed for', audioPath, analyzeError);
                    processingProgress.value.status = `Analysis failed: ${analyzeError.message || 'Unknown error'}`;
                    processingProgress.value.percent = 100;
                    
                    // Continue with next file
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }

            currentProcessingPath.value = null;
            processingProgress.value = null;
            message.value = 'Batch analysis complete.';
            await loadAudioFiles();
        };

        const cancelBatchAnalysis = () => {
            processingQueue.value = [];
            currentProcessingPath.value = null;
            processingProgress.value = null;
            message.value = '';
        };

        const openCrmForm = async (audioFile, viewOnly = false) => {
            // Try in-memory result first, then fall back to fetching from backend
            let result = analysisResults[audioFile.path];

            if (!result) {
                // Already analyzed (page refresh) — fetch the result paths from backend
                try {
                    result = await apiClient.get(`/audio/analyze-result?audio_path=${encodeURIComponent(audioFile.path)}`);
                    if (result) {
                        analysisResults[audioFile.path] = result;
                    }
                } catch (fetchErr) {
                    console.error('Could not fetch existing analysis result', fetchErr);
                }
            }

            if (!result) {
                error.value = 'No analysis result found. Please analyze this file first.';
                return;
            }

            const htmlPath = result.crm_form_html_path || result.result?.crm_form_html_path || '';
            if (!htmlPath) {
                error.value = 'No CRM form HTML is available yet.';
                return;
            }

            // Don't auto-submit on open — the user submits via the form's Save button

            try {
                const response = await apiClient.request(`/audio/file-content?path=${encodeURIComponent(htmlPath)}`);
                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(errText || `Failed to open CRM form: ${response.status}`);
                }

                const data = await response.json();
                let htmlContent = data.content || '';

                // Inject auth token, save URL, and audio filename so the popup can POST back on submit
                const { config } = await import('../config.js');
                const saveUrl = `${config.getApiBaseUrl()}/audio/crm-form/save`;
                const authToken = sessionStorage.getItem('auth_token') || '';
                const readOnlyFlag = viewOnly ? 'true' : 'false';

                // When opening in view-only mode, fetch the actual submitted form data
                let initialDataScript = '';
                if (viewOnly) {
                    try {
                        const submittedData = await apiClient.get(`/audio/crm-form-submitted-data?audio_filename=${encodeURIComponent(audioFile.name)}`);
                        if (submittedData && submittedData.form) {
                            initialDataScript = `<script>window.crmSubmittedFormData = ${JSON.stringify(submittedData.form)};<\/script>`;
                        }
                    } catch (fetchErr) {
                        console.warn('Could not fetch submitted form data, opening with original data', fetchErr);
                    }
                }

                const tokenScript = `<script>window.crmSaveUrl = ${JSON.stringify(saveUrl)};window.crmAuthToken = ${JSON.stringify(authToken)};window.crmAudioFilename = ${JSON.stringify(audioFile.name)};window.crmReadOnly = ${readOnlyFlag};<\/script>${initialDataScript}`;

                if (htmlContent.includes('</head>')) {
                    htmlContent = htmlContent.replace('</head>', `${tokenScript}</head>`);
                } else {
                    htmlContent = tokenScript + htmlContent;
                }

                const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
                const blobUrl = URL.createObjectURL(blob);
                const popup = window.open(blobUrl, '_blank');
                if (!popup) {
                    // Fallback: open in same tab if popup is blocked
                    window.location.href = blobUrl;
                    return;
                }
                setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
            } catch (openError) {
                console.error('Failed to open CRM form', openError);
                error.value = openError.message || 'Failed to open CRM form.';
            }
        };

        const showLangDropdown = ref(false);
        const languages = languageService.LANGUAGES;
        const currentLanguage = languageService.currentLanguage;
        const changeLanguage = async (code) => { showLangDropdown.value = false; await languageService.setLanguage(code); };
        const getLanguageLabel = languageService.getLanguageLabel;

        const showProfileMenu = ref(false);
        const userInitial = computed(() => (authService.getUser()?.username || 'U')[0].toUpperCase());
        const switchToAdmin = () => {
            authService.switchRole('admin');
            router.push({ name: 'admin_dashboard' });
        };

        onMounted(() => {
            loadAudioFiles();
            window.addEventListener('message', async (event) => {
                if (!event.data || !event.data.type) return;
                if (event.data.type === 'crm-form-save') {
                    try {
                        await apiClient.post('/audio/crm-form/save', event.data.payload);
                        event.source.postMessage({ type: 'crm-form-save-result', success: true }, '*');
                        loadSubmissionStatuses();
                    } catch (err) {
                        event.source.postMessage({ type: 'crm-form-save-result', success: false, error: err.message || 'Save failed' }, '*');
                    }
                }
            });
        });

        return {
            fileInput, isUploading, uploadProgress, message, error, chooseAudio, uploadAudio, logout,
            audioFiles, completedAudioFiles, newAudioFiles,
            selectedPaths, isAnalyzing, selectAllChecked, selectAllIndeterminate,
            processingProgress, analysisResults, crmFormStatusCache, submittedAudioFiles,
            loadAudioFiles, toggleAudioSelection, toggleSelectAll, startBatchAnalysis, cancelBatchAnalysis,
            isCrmFormAvailable, openCrmForm, parseAudioFileInfo, isSubmitted,
            showLangDropdown, languages, currentLanguage, changeLanguage, getLanguageLabel,
            showProfileMenu, userInitial, switchToAdmin,
        };
    },
    template: `
    <div class="min-h-screen bg-gray-50">

      <!-- ── Sticky Header ── -->
      <div class="sticky top-0 z-10 bg-white border-b border-gray-200">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 class="text-2xl font-semibold text-slate-800">User Dashboard</h1>
            <p class="text-slate-500 text-sm">Autofill CRM Form</p>
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
                <button v-for="lang in languages" :key="lang.code"
                  @click="changeLanguage(lang.code)"
                  :class="['w-full text-left px-4 py-2 text-sm hover:bg-gray-50 transition', currentLanguage === lang.code ? 'text-blue-600 font-medium bg-blue-50' : 'text-slate-700']">
                  {{ lang.label }}
                </button>
              </div>
            </div>
            <button @click="chooseAudio" :disabled="isUploading"
              class="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition text-sm font-medium disabled:opacity-50">
              {{ isUploading ? 'Uploading...' : 'Upload Audio' }}
            </button>
            <button @click="loadAudioFiles"
              class="px-4 py-2 rounded-lg border border-gray-200 text-slate-600 hover:bg-gray-50 transition text-sm font-medium">
              Refresh
            </button>
            <!-- Profile Icon -->
            <div class="relative">
              <button @click="showProfileMenu = !showProfileMenu"
                class="w-9 h-9 rounded-full bg-slate-800 text-white flex items-center justify-center text-sm font-semibold hover:bg-slate-700 transition">
                {{ userInitial }}
              </button>
              <div v-if="showProfileMenu" class="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-30">
                <button @click="switchToAdmin" class="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-gray-50 transition">Switch to Admin</button>
                <button @click="logout" class="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition">Logout</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <input ref="fileInput" type="file" accept="audio/*" class="sr-only" @change="uploadAudio">

      <!-- ── Status messages ── -->
      <div class="max-w-7xl mx-auto px-6 pt-4">
        <div v-if="isUploading" class="mb-4">
          <div class="w-full h-2 rounded-full bg-gray-200 overflow-hidden">
            <div class="h-full bg-blue-600 rounded-full transition-all duration-300" :style="{ width: uploadProgress + '%' }"></div>
          </div>
          <p class="text-sm text-gray-500 mt-1">Uploading {{ uploadProgress }}%</p>
        </div>
        <div v-if="message" class="mb-4 px-4 py-3 rounded-xl bg-blue-50 border border-blue-200 text-blue-700 text-sm">{{ message }}</div>
      </div>

      <!-- ── Processing progress ── -->
      <div v-if="isAnalyzing" class="max-w-7xl mx-auto px-6 mb-6">
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="flex items-center justify-between mb-3">
            <span class="text-sm font-medium text-gray-700">{{ processingProgress?.status || 'Processing...' }}</span>
            <button @click="cancelBatchAnalysis"
              class="px-3 py-1.5 rounded-lg border border-red-300 text-red-600 hover:bg-red-50 text-xs font-medium transition">
              Cancel
            </button>
          </div>
          <div class="w-full h-2 rounded-full bg-gray-200 overflow-hidden">
            <div class="h-full bg-blue-600 rounded-full animate-pulse" style="width: 60%"></div>
          </div>
        </div>
      </div>

      <!-- ── Side-by-side floating cards ── -->
      <div class="max-w-7xl mx-auto px-6 pb-10 grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">

        <!-- LEFT CARD: New Audios -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <!-- Card header -->
          <div class="px-6 py-4 border-b border-gray-200 bg-gray-50">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center">
                  <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
                  </svg>
                </div>
                <div>
                  <h2 class="text-lg font-semibold text-slate-800">New Audios</h2>
                  <p class="text-xs text-slate-500">Select and analyze pending recordings</p>
                </div>
              </div>
              <button v-if="!isAnalyzing && newAudioFiles.length > 0"
                @click="startBatchAnalysis"
                :disabled="selectedPaths.size === 0"
                class="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition disabled:opacity-40 disabled:cursor-not-allowed shadow-sm">
                Analyze ({{ selectedPaths.size }})
              </button>
            </div>
          </div>
          <!-- Card body -->
          <div class="p-0">
            <div v-if="!isAnalyzing && newAudioFiles.length > 0" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                    <th class="px-4 py-3 w-12">
                      <input type="checkbox" @change="toggleSelectAll"
                        :checked="selectAllChecked" :indeterminate="selectAllIndeterminate"
                        class="w-4 h-4 cursor-pointer accent-blue-600 rounded" />
                    </th>
                    <th class="px-4 py-3">S.No.</th>
                    <th class="px-4 py-3">Audio File</th>
                    <th class="px-4 py-3 text-center">CRM Form</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(audioFile, index) in newAudioFiles" :key="audioFile.path"
                    class="border-b border-gray-50 hover:bg-gray-50 transition cursor-pointer"
                    @click="toggleAudioSelection(audioFile.path)">
                    <td class="px-4 py-3">
                      <input type="checkbox"
                        :checked="selectedPaths.has(audioFile.path)"
                        @click.stop="toggleAudioSelection(audioFile.path)"
                        class="w-4 h-4 cursor-pointer accent-blue-600 rounded" />
                    </td>
                    <td class="px-4 py-3 text-gray-500">{{ index + 1 }}</td>
                    <td class="px-4 py-3 font-medium text-gray-800">{{ parseAudioFileInfo(audioFile).name }}</td>
                    <td class="px-4 py-3 text-center">
                      <button @click.stop="openCrmForm(audioFile)"
                        :disabled="!isCrmFormAvailable(audioFile)"
                        class="px-3 py-1.5 rounded-lg border text-xs font-medium transition shadow-sm"
                        :class="isCrmFormAvailable(audioFile)
                          ? 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700'
                          : 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'">
                        Open CRM
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else-if="!isAnalyzing && newAudioFiles.length === 0 && completedAudioFiles.length > 0" class="px-6 py-12 text-center">
              <div class="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
              </div>
              <p class="text-gray-500 text-sm font-medium">All audio files have been analyzed</p>
            </div>
            <div v-else-if="!isAnalyzing" class="px-6 py-12 text-center">
              <div class="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
                </svg>
              </div>
              <p class="text-gray-400 text-sm">No audio files found. Upload some to get started.</p>
            </div>
          </div>
        </div>

        <!-- RIGHT CARD: Completed Audio Analysis -->
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <!-- Card header -->
          <div class="px-6 py-4 border-b border-gray-200 bg-gray-50">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center">
                <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <div>
                <h2 class="text-lg font-semibold text-slate-800">Completed Audio Analysis</h2>
                <p class="text-xs text-slate-500">Analyzed recordings with CRM forms ready</p>
              </div>
            </div>
          </div>
          <!-- Card body -->
          <div class="p-0">
            <div v-if="completedAudioFiles.length > 0" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                    <th class="px-4 py-3">S.No.</th>
                    <th class="px-4 py-3">Audio File</th>
                    <th class="px-4 py-3 text-center">Status</th>
                    <th class="px-4 py-3 text-center">Action</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(audioFile, index) in completedAudioFiles" :key="audioFile.path"
                    class="border-b border-gray-50 hover:bg-gray-50 transition">
                    <td class="px-4 py-3 text-gray-500">{{ index + 1 }}</td>
                    <td class="px-4 py-3 font-medium text-gray-800">{{ parseAudioFileInfo(audioFile).name }}</td>
                    <td class="px-4 py-3 text-center">
                      <span v-if="isSubmitted(audioFile)" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-green-50 text-green-700 text-xs font-medium">
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
                        Submitted
                      </span>
                      <span v-else class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 text-xs font-medium">
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/></svg>
                        Pending
                      </span>
                    </td>
                    <td class="px-4 py-3 text-center">
                      <div class="flex items-center justify-center gap-2">
                        <button v-if="!isSubmitted(audioFile)" @click="openCrmForm(audioFile)"
                          class="px-3 py-1.5 rounded-lg bg-slate-800 text-white text-xs font-medium hover:bg-slate-700 transition shadow-sm">
                          Open CRM
                        </button>
                        <button v-if="isSubmitted(audioFile)" @click="openCrmForm(audioFile, true)"
                          class="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition shadow-sm">
                          View CRM
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="px-6 py-12 text-center">
              <div class="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
              </div>
              <p class="text-gray-400 text-sm">No completed analyses yet</p>
            </div>
          </div>
        </div>

      </div>
    </div>
    `,
};
