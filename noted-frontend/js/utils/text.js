/**
 * Shared text utilities — extracted from dashboard.js and recording_view.js
 */

/**
 * Clean transcript text by removing unwanted tokens and formatting artifacts.
 */
export function cleanTranscriptText(text) {
    if (!text) return '';

    return text
        .replace(/<\|endoftext\|>/g, '')
        .replace(/<\|\d+\|>/g, '')
        .replace(/Please Repeat/gi, '')
        .replace(/\[Speaker \d+ \d+:\d+\]:\s*/g, '')
        .replace(/\[UNKNOWN \d+:\d+\]:\s*/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

/**
 * Normalize speaker label — handle UNKNOWN speakers.
 */
export function normalizeSpeaker(speaker) {
    if (!speaker || speaker.toLowerCase().includes('unknown')) {
        return 'Unknown';
    }
    const s = speaker.toLowerCase().trim();
    if (s === 'advisor' || s.includes('advisor') || s === 'assistant' || s.includes('assistant')) return 'Advisor';
    if (s === 'customer') return 'Customer';
    // Fallback for raw labels not yet classified
    if (s === '0' || s.includes('speaker_00') || s === 'speaker_0' || s === 'speaker 0') return 'Speaker 0';
    if (s === '1' || s.includes('speaker_01') || s === 'speaker_1' || s === 'speaker 1') return 'Speaker 1';
    return speaker;
}

/**
 * Format seconds into HH:MM:SS or MM:SS.
 */
export function formatTime(seconds) {
    if (!seconds && seconds !== 0) return '00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

/**
 * Format a timestamp string or Date into a readable date.
 */
export function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleDateString().replace(/\//g, '-');
}

/**
 * Format seconds into HH:MM:SS or MM:SS (for transcript timestamps).
 */
export function formatSecondsTimestamp(seconds) {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hours > 0) {
        return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}
