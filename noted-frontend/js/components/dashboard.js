import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { sessionService } from '../services/session_service.js';

export default {
    name: 'Dashboard',
    setup() {
        const router = useRouter();
        const fileInput = ref(null);
        const isUploading = ref(false);
        const uploadProgress = ref(0);
        const message = ref('');
        const error = ref('');

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
            } catch (uploadError) {
                error.value = uploadError.message || 'Unable to upload the audio file.';
            } finally {
                isUploading.value = false;
                event.target.value = '';
            }
        };

        return { fileInput, isUploading, uploadProgress, message, error, chooseAudio, uploadAudio, logout };
    },
    template: `
        <main class="audio-upload-dashboard">
            <button type="button" class="logout-button" @click="logout">Logout</button>
            <input
                ref="fileInput"
                type="file"
                accept="audio/*"
                class="sr-only"
                @change="uploadAudio"
            >
            <button type="button" class="upload-button" :disabled="isUploading" @click="chooseAudio">
                {{ isUploading ? 'Uploading…' : 'Upload audio' }}
            </button>
            <div v-if="isUploading" class="upload-progress" role="progressbar" :aria-valuenow="uploadProgress" aria-valuemin="0" aria-valuemax="100">
                <div class="upload-progress__bar" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <p v-if="isUploading" class="status">Uploading {{ uploadProgress }}%</p>
            <p v-if="message" class="status success">{{ message }}</p>
            <p v-if="error" class="status error">{{ error }}</p>
        </main>
    `,
};
