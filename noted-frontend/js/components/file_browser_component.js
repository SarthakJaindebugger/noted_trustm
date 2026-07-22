import { ref, computed, onMounted } from 'vue';
import { apiClient } from '../services/api_client.js';
import { useRouter } from 'vue-router';

export default {
  name: 'FileBrowserView',
  setup() {
    const router = useRouter();
    const currentPath = ref('');
    const entries = ref([]);
    const selectedFile = ref(null);
    const fileContent = ref('');
    const previewExtension = ref('');
    const error = ref('');
    const loading = ref(false);
    const previewLoading = ref(false);

    const breadcrumb = computed(() => {
      const parts = currentPath.value.split('/').filter(Boolean);
      return [{ name: 'noted-main', path: '' }, ...parts.map((part, idx) => ({
        name: part,
        path: parts.slice(0, idx + 1).join('/'),
      }))];
    });

    const formatSize = (size) => {
      if (size == null) return '—';
      if (size < 1024) return `${size} B`;
      if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
      return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    };

    const fetchEntries = async (path = '') => {
      loading.value = true;
      error.value = '';
      try {
        const response = await apiClient.get(`/admin/files${path ? `?path=${encodeURIComponent(path)}` : ''}`);
        currentPath.value = response.path || '';
        entries.value = response.entries || [];
        selectedFile.value = null;
        fileContent.value = '';
        previewExtension.value = '';
      } catch (err) {
        console.error('Failed to load entries', err);
        error.value = err.message || 'Failed to load directory';
      } finally {
        loading.value = false;
      }
    };

    const loadFile = async (entry) => {
      if (!entry || entry.is_dir) {
        return;
      }
      previewLoading.value = true;
      error.value = '';
      try {
        const response = await apiClient.get(`/admin/files/content?path=${encodeURIComponent(entry.path)}`);
        selectedFile.value = entry;
        fileContent.value = response.content || '';
        previewExtension.value = response.extension || '';
      } catch (err) {
        console.error('Failed to load file content', err);
        error.value = err.message || 'Failed to load file content';
      } finally {
        previewLoading.value = false;
      }
    };

    const goToEntry = async (entry) => {
      if (entry.is_dir) {
        await fetchEntries(entry.path);
      } else {
        await loadFile(entry);
      }
    };

    const goUp = async () => {
      const parts = currentPath.value.split('/').filter(Boolean);
      if (parts.length <= 1) {
        await fetchEntries('');
        return;
      }
      await fetchEntries(parts.slice(0, -1).join('/'));
    };

    onMounted(() => {
      fetchEntries('');
    });

    return {
      currentPath,
      entries,
      selectedFile,
      fileContent,
      previewExtension,
      error,
      loading,
      previewLoading,
      breadcrumb,
      fetchEntries,
      goToEntry,
      goUp,
      formatSize,
      router,
    };
  },
  template: `
    <div class="min-h-screen bg-slate-50">
      <div class="sticky top-0 z-20 bg-slate-950 text-slate-100 border-b border-slate-800">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 class="text-2xl font-semibold">Raw Backend Access</h1>
            <p class="text-sm text-slate-400">VS Code style explorer for raw repo and user data access.</p>
          </div>
          <button @click="router.push({ name: 'admin_dashboard' })" class="rounded-xl bg-slate-700 text-white px-4 py-2 hover:bg-slate-600 transition">
            Back to Admin Dashboard
          </button>
        </div>
      </div>

      <div class="max-w-7xl mx-auto px-6 py-6 grid gap-6 lg:grid-cols-[320px_1fr]">
        <div class="bg-slate-900 text-slate-100 shadow-lg rounded-2xl overflow-hidden border border-slate-800">
          <div class="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
            <div>
              <h2 class="text-sm font-semibold">Explorer</h2>
              <p class="text-xs text-slate-400">noted-main</p>
            </div>
            <button @click="goUp" class="text-sm text-slate-300 hover:text-white">Up</button>
          </div>
          <div class="px-5 py-3 border-b border-slate-200 text-xs text-slate-500">
            <div class="flex flex-wrap gap-2">
              <span v-for="(crumb, idx) in breadcrumb" :key="crumb.path" class="rounded-full bg-slate-100 px-3 py-1 text-slate-600 cursor-pointer hover:bg-slate-200"
                @click="fetchEntries(crumb.path)">
                {{ crumb.name }}
              </span>
            </div>
          </div>
          <div class="max-h-[680px] overflow-y-auto bg-slate-950 text-slate-100">
            <table class="min-w-full text-left text-sm">
              <tbody>
                <tr v-if="loading" class="border-b border-slate-800">
                  <td colspan="3" class="px-4 py-4 text-slate-400">Loading directory...</td>
                </tr>
                <tr v-if="!loading && entries.length === 0" class="border-b border-slate-800">
                  <td colspan="3" class="px-4 py-4 text-slate-400">No files or folders in this directory.</td>
                </tr>
                <tr v-for="entry in entries" :key="entry.path" class="cursor-pointer border-b border-slate-800 hover:bg-slate-800" @click="goToEntry(entry)">
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-2">
                      <span class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-slate-800 text-slate-300">
                        <span v-if="entry.is_dir">📁</span>
                        <span v-else>📄</span>
                      </span>
                      <div class="max-w-[180px] truncate">{{ entry.name }}</div>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-slate-400">{{ entry.is_dir ? 'Folder' : entry.extension.toUpperCase() }}</td>
                  <td class="px-4 py-3 text-right text-slate-400">{{ formatSize(entry.size) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="bg-white shadow-sm rounded-2xl border border-slate-200 overflow-hidden flex flex-col">
          <div class="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
            <div>
              <h2 class="text-sm font-semibold text-slate-900">Preview</h2>
              <p class="text-xs text-slate-500">Click a supported file to open it in read-only mode.</p>
            </div>
            <div class="text-xs text-slate-500">{{ selectedFile?.name || 'No file selected' }}</div>
          </div>

          <div class="p-6 flex-1 overflow-hidden bg-slate-950 text-slate-100">
            <div v-if="error" class="rounded-2xl border border-red-600 bg-red-900/20 p-4 text-sm text-red-200">{{ error }}</div>
            <div v-else-if="previewLoading" class="text-slate-400">Loading file preview...</div>
            <div v-else-if="!selectedFile" class="h-full flex items-center justify-center text-slate-400">
              Select a file to preview its contents.
            </div>
            <div v-else class="h-full overflow-auto bg-slate-950 text-slate-100 rounded-2xl p-4 border border-slate-800">
              <div class="mb-4 flex items-center justify-between gap-3 border-b border-slate-800 pb-3">
                <div>
                  <div class="text-sm text-slate-300">{{ selectedFile.name }}</div>
                  <div class="text-xs text-slate-500">{{ selectedFile.path }}</div>
                </div>
                <div class="text-xs uppercase tracking-[0.15em] text-slate-500">{{ previewExtension || selectedFile.extension }}</div>
              </div>
              <pre class="whitespace-pre-wrap break-words text-xs leading-5 font-mono text-slate-100">{{ fileContent }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
};
