const express = require('express');
const app = express();
const port = 3000;

// Middleware to parse JSON bodies
app.use(express.json());

// Serve static files (HTML, CSS, JS)
app.use(express.static('public'));

// Mock database - in a real app, this would connect to your actual database
let audios = [
    { id: 1, name: 'meeting_recording.wav', uploadDate: '2024-01-15', analyzed: false },
    { id: 2, name: 'podcast_episode.mp3', uploadDate: '2024-01-14', analyzed: true, analysisDate: '2024-01-16' },
    { id: 3, name: 'interview_audio.flac', uploadDate: '2024-01-13', analyzed: false },
    { id: 4, name: 'lecture_sound.mp4', uploadDate: '2024-01-12', analyzed: true, analysisDate: '2024-01-14' },
    { id: 5, name: 'conference_call.aac', uploadDate: '2024-01-11', analyzed: false },
    // Add more audio entries as needed
];

// GET endpoint to fetch unanalyzed audios
app.get('/api/unanalyzed-audios', (req, res) => {
    try {
        const unanalyzedAudios = audios.filter(audio => !audio.analyzed);
        res.status(200).json({
            success: true,
            data: unanalyzedAudios
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error fetching unanalyzed audios',
            error: error.message
        });
    }
});

// GET endpoint to fetch analyzed audios
app.get('/api/analyzed-audios', (req, res) => {
    try {
        const analyzedAudios = audios.filter(audio => audio.analyzed);
        res.status(200).json({
            success: true,
            data: analyzedAudios
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error fetching analyzed audios',
            error: error.message
        });
    }
});

// POST endpoint to add a new audio (for upload simulation)
app.post('/api/upload-audio', (req, res) => {
    try {
        const { name, uploadDate } = req.body;
        const newAudio = {
            id: audios.length + 1,
            name,
            uploadDate,
            analyzed: false
        };
        audios.push(newAudio);
        res.status(201).json({
            success: true,
            message: 'Audio uploaded successfully',
            data: newAudio
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error uploading audio',
            error: error.message
        });
    }
});

// POST endpoint to analyze an audio
app.post('/api/analyze-audio/:id', (req, res) => {
    try {
        const audioId = parseInt(req.params.id);
        const audioIndex = audios.findIndex(audio => audio.id === audioId);
        
        if (audioIndex === -1) {
            return res.status(404).json({
                success: false,
                message: 'Audio not found'
            });
        }
        
        // Update the audio to mark as analyzed
        audios[audioIndex].analyzed = true;
        audios[audioIndex].analysisDate = new Date().toISOString().split('T')[0];
        
        res.status(200).json({
            success: true,
            message: 'Audio analyzed successfully',
            data: audios[audioIndex]
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            message: 'Error analyzing audio',
            error: error.message
        });
    }
});

// Start the server
app.listen(port, () => {
    console.log(`Server running at http://localhost:${port}`);
    console.log(`API Endpoints:`);
    console.log(`GET    http://localhost:${port}/api/unanalyzed-audios`);
    console.log(`GET    http://localhost:${port}/api/analyzed-audios`);
    console.log(`POST   http://localhost:${port}/api/upload-audio`);
    console.log(`POST   http://localhost:${port}/api/analyze-audio/:id`);
});