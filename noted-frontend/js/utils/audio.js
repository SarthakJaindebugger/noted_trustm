/**
 * Shared audio utilities — extracted from recording_service.js and recording_view.js
 */

/**
 * Resample audio from one sample rate to another using linear interpolation.
 * @param {Float32Array} audioData - Input audio samples
 * @param {number} fromRate - Source sample rate
 * @param {number} toRate - Target sample rate
 * @returns {Float32Array} Resampled audio
 */
export function resampleAudio(audioData, fromRate, toRate) {
    if (fromRate === toRate) {
        return audioData;
    }

    const ratio = fromRate / toRate;
    const newLength = Math.round(audioData.length / ratio);
    const result = new Float32Array(newLength);

    for (let i = 0; i < newLength; i++) {
        const position = i * ratio;
        const index = Math.floor(position);
        const fraction = position - index;

        if (index + 1 < audioData.length) {
            result[i] = audioData[index] * (1 - fraction) + audioData[index + 1] * fraction;
        } else {
            result[i] = audioData[index] || 0;
        }
    }

    return result;
}
