import { ref } from 'vue';
import { sessionService } from '../services/session_service.js';
import { registerCJKFont } from '../utils/pdf.js';

export function useDashboardExports({
    selectedSessionRef,
    topics,
    sessionSummary,
    translatedLanguage,
    selectedLanguage,
    showNotification,
}) {
    const showPdfPreviewModal = ref(false);
    const pdfPreviewUrl = ref('');
    const isGeneratingPdf = ref(false);

    const showPdfPreview = (pdfBlob) => {
        if (pdfPreviewUrl.value) {
            URL.revokeObjectURL(pdfPreviewUrl.value);
        }

        pdfPreviewUrl.value = URL.createObjectURL(pdfBlob);
        showPdfPreviewModal.value = true;
    };

    const closePdfPreviewModal = () => {
        showPdfPreviewModal.value = false;

        if (pdfPreviewUrl.value) {
            URL.revokeObjectURL(pdfPreviewUrl.value);
            pdfPreviewUrl.value = '';
        }
    };

    const generatePDF = async (isPreview = false) => {
        const translatedTopics = topics.value;
        const translatedSummary = sessionSummary.value;
        const activeLanguage = translatedLanguage.value || 'English';

        const { jsPDF } = window.jspdf || {};
        if (!jsPDF) {
            throw new Error('PDF generator (jsPDF) not available.');
        }

        const doc = new jsPDF();
        await registerCJKFont(doc);

        const pageWidth = doc.internal.pageSize.getWidth();
        const pageHeight = doc.internal.pageSize.getHeight();
        const margin = 20;
        const contentWidth = pageWidth - (margin * 2);
        let yPosition = margin;

        const addWrappedText = (text, fontSize = 12, isBold = false) => {
            doc.setFontSize(fontSize);
            doc.setFont('NotoSansCJK', isBold ? 'bold' : 'normal');

            const lines = doc.splitTextToSize(text, contentWidth);
            if (yPosition + (lines.length * fontSize * 0.6) > pageHeight - margin) {
                doc.addPage();
                yPosition = margin;
            }

            lines.forEach(line => {
                doc.text(line, margin, yPosition);
                yPosition += fontSize * 0.6;
            });
            yPosition += 5;
        };

        addWrappedText('Session Summary', 20, true);
        addWrappedText(`Session: ${selectedSessionRef.value || 'Unknown'}`, 12);
        addWrappedText(`Date: ${new Date().toLocaleDateString()}`, 12);
        addWrappedText(`Generated: ${new Date().toLocaleString()}`, 12);
        addWrappedText(`Content Language: ${activeLanguage}`, 12);

        yPosition += 10;
        doc.setLineWidth(0.5);
        doc.line(margin, yPosition, pageWidth - margin, yPosition);
        yPosition += 15;

        const overviewText = translatedSummary?.overview || '';
        if (overviewText) {
            addWrappedText('Executive Summary', 16, true);
            addWrappedText(overviewText, 12);
            yPosition += 10;
        }

        addWrappedText('Topics Discussed', 16, true);

        if (translatedTopics && translatedTopics.length > 0) {
            translatedTopics.forEach((topic, index) => {
                addWrappedText(`Topic ${index + 1}: ${topic.reference || topic.topic || `Topic ${index + 1}`}`, 12, true);
                if (topic.tags && topic.tags.length > 0) {
                    addWrappedText(`Tags: ${topic.tags.join(', ')}`, 10);
                }
                addWrappedText(`Summary: ${topic.content || topic.summary || 'No summary available'}`, 12);

                if (topic.key_points && topic.key_points.length > 0) {
                    addWrappedText('Key Points:', 12, true);
                    topic.key_points.forEach(point => {
                        addWrappedText(`• ${point}`, 11);
                    });
                }

                if (topic.action_items && topic.action_items.length > 0) {
                    addWrappedText('Action Items:', 12, true);
                    topic.action_items.forEach(item => {
                        addWrappedText(`• ${item}`, 11);
                    });
                }

                yPosition += 8;
            });
        } else {
            addWrappedText('No topics discussed in this session.', 12);
        }

        if (translatedSummary && translatedSummary.action_items && translatedSummary.action_items.length > 0) {
            yPosition += 10;
            addWrappedText('Action Items', 16, true);
            translatedSummary.action_items.forEach(item => {
                const taskText = typeof item === 'object' ? item.task : item;
                const responsible = typeof item === 'object' ? item.responsible_party : '';
                const timeline = typeof item === 'object' ? item.timeline : '';

                addWrappedText(`• ${taskText}`, 12);
                if (responsible) {
                    addWrappedText(`  Responsible: ${responsible}`, 11);
                }
                if (timeline) {
                    addWrappedText(`  Timeline: ${timeline}`, 11);
                }
            });
        }

        yPosition += 10;
        addWrappedText('Translation Language', 16, true);
        addWrappedText(activeLanguage, 12);

        const footerY = pageHeight - margin;
        doc.setFontSize(10);
        doc.setFont('NotoSansCJK', 'normal');
        doc.text('Generated by Note\'d - Service Recording Platform', margin, footerY);

        if (isPreview) {
            showPdfPreview(doc.output('blob'));
            return;
        }

        const sessionLabel = selectedSessionRef.value || 'session';
        const safeLanguage = activeLanguage.replace(/\s+/g, '-');
        const filename = safeLanguage
            ? `session-summary-${sessionLabel}-${safeLanguage}.pdf`
            : `session-summary-${sessionLabel}.pdf`;
        doc.save(filename);
    };

    const previewPDF = async () => {
        if (isGeneratingPdf.value) {
            return;
        }

        isGeneratingPdf.value = true;
        try {
            await generatePDF(true);
        } catch (error) {
            console.error('Failed to preview PDF:', error);
            showNotification('Error', `Failed to preview PDF: ${error.message}`, 'error');
        } finally {
            isGeneratingPdf.value = false;
        }
    };

    const downloadPDF = async () => {
        if (isGeneratingPdf.value) {
            return;
        }

        isGeneratingPdf.value = true;
        try {
            await generatePDF(false);
        } catch (error) {
            console.error('Failed to generate PDF:', error);
            showNotification('Error', `Failed to generate PDF: ${error.message}`, 'error');
        } finally {
            isGeneratingPdf.value = false;
        }
    };

    const downloadSessionData = async (sessionId) => {
        try {
            const transcript = await sessionService.getSessionTranscript(sessionId);
            const sessionData = {
                session_id: sessionId,
                transcript,
                export_date: new Date().toISOString(),
                topics: topics.value,
                language_selection: selectedLanguage.value,
            };

            const blob = new Blob([JSON.stringify(sessionData, null, 2)], { type: 'application/json' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `session-data-${sessionId}.json`;
            link.click();
            URL.revokeObjectURL(link.href);
        } catch (error) {
            console.error('Failed to download session data:', error);
            showNotification('Error', 'Failed to download session data. Please try again.', 'error');
        }
    };

    return {
        showPdfPreviewModal,
        pdfPreviewUrl,
        isGeneratingPdf,
        previewPDF,
        downloadPDF,
        downloadSessionData,
        closePdfPreviewModal,
    };
}
