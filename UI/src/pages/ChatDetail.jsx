import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Paper,
  TextField,
  Button,
  Typography,
  Stack,
  IconButton,
  CircularProgress,
  Alert,
  Tooltip,
  Divider,
  Chip,
  Fade,
  Slide,
  Card,
  CardContent,
  CardHeader,
  Avatar,
} from '@mui/material';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { materialLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import PersonIcon from '@mui/icons-material/Person';
import { projectApi, chatApi } from '../services/api';

function ChatDetail({ onError }) {
  const { projectId, chatId } = useParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [addingSample, setAddingSample] = useState(null);
  const [feedbackEnabled, setFeedbackEnabled] = useState(null);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [sampleAdded, setSampleAdded] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadProjectAndChat();
  }, [projectId, chatId]);

  const loadProjectAndChat = async () => {
    try {
      const projectData = await projectApi.getProject(projectId);
      setProject(projectData);

      const currentChat = await chatApi.getChat(chatId);
      if (!currentChat) {
        throw new Error('Chat not found');
      }

      // Convert query_history to messages format
      const historyWithIds = (currentChat.query_history || []).map((msg, index) => ({
        id: msg.id || Date.now() + index,
        text: msg.text,
        sql: msg.sql,
        timestamp: msg.timestamp,
        correct: msg.is_correct || null
      }));

      setMessages(historyWithIds);
      setFeedbackEnabled(currentChat.feedback_enabled);
    } catch (err) {
      onError(err);
    } finally {
      setLoading(false);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => scrollToBottom(), 100);
    }
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || generating) return;

    const newMessage = {
      id: Date.now(),
      text: input,
      sql: null,
      correct: null,
    };

    setMessages(prev => [...prev, newMessage]);
    setInput('');
    setGenerating(true);
    scrollToBottom();

    try {
      const response = await chatApi.generateSql(chatId, input);
      setMessages(prev => prev.map(msg =>
        msg.id === newMessage.id
          ? { ...msg, sql: response.sql }
          : msg
      ));
      scrollToBottom();
    } catch (err) {
      onError(err);
      setMessages(prev => prev.filter(msg => msg.id !== newMessage.id));
    } finally {
      setGenerating(false);
    }
  };

  const handleFeedback = async (messageId, isCorrect) => {
    try {
      setMessages(prev => prev.map(msg =>
        msg.id === messageId
          ? { ...msg, correct: isCorrect }
          : msg
      ));

      const response = await chatApi.feedback(chatId, {
        is_correct: isCorrect,
        add_to_samples: false
      });

      // Update feedback_enabled based on the response
      if (response.feedback_enabled !== undefined) {
        setFeedbackEnabled(response.feedback_enabled);
      }

      setFeedbackSubmitted(true);
      setTimeout(() => setFeedbackSubmitted(false), 2000);

      // If marked as incorrect and new SQL is provided, add it to messages
      if (!isCorrect && response.sql) {
        const newMessage = {
          id: Date.now(),
          text: messages.find(msg => msg.id === messageId)?.text || '',
          sql: response.sql,
          correct: null,
        };
        setMessages(prev => [...prev, newMessage]);
        scrollToBottom();
      }
    } catch (err) {
      onError(err);
      setMessages(prev => prev.map(msg =>
        msg.id === messageId
          ? { ...msg, correct: null }
          : msg
      ));
    }
  };

  const handleAddSample = async (messageId) => {
    const message = messages.find(m => m.id === messageId);
    if (!message || addingSample === messageId) return;

    setAddingSample(messageId);
    try {
      // Update chat to add the last query to samples
      const response = await chatApi.updateChat(chatId, {
        last_query_feedback: true,
        add_to_samples: true
      });

      // Update feedback_enabled based on the response
      if (response.feedback_enabled !== undefined) {
        setFeedbackEnabled(response.feedback_enabled);
      }

      // Show success notification
      setSampleAdded(true);
      setTimeout(() => setSampleAdded(false), 2000);
    } catch (err) {
      onError(err);
    } finally {
      setAddingSample(null);
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  // Helper function to check if this is the last SQL message
  const isLastSqlMessage = (messageIndex) => {
    const sqlMessages = messages.filter(msg => msg.sql);
    const currentMessage = messages[messageIndex];
    return currentMessage.sql && sqlMessages[sqlMessages.length - 1].id === currentMessage.id;
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{
      width: '100%',
      height: 'calc(100vh - 120px)',
      display: 'flex',
      flexDirection: 'column'
    }}>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(`/project/${projectId}/chat`)}
          variant="outlined"
          size="small"
        >
          Back to Project
        </Button>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          {project?.name} - Chat {chatId}
        </Typography>
      </Box>

      {/* Chat Card */}
      <Card sx={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 2,
        backgroundColor: '#fafafa',
        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
      }}>
        <CardHeader
          title="SQL Generator Chat"
          subheader={`Project: ${project?.name}`}
          sx={{
            backgroundColor: 'primary.main',
            color: 'white',
            '& .MuiCardHeader-title': { color: 'white' },
            '& .MuiCardHeader-subheader': { color: 'rgba(255,255,255,0.8)' }
          }}
        />

        <CardContent sx={{
          flex: 1,
          p: 3,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          backgroundColor: '#f8f9fa'
        }}>
          {messages.length === 0 ? (
            <Box sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              textAlign: 'center',
              color: 'text.secondary'
            }}>
              <SmartToyIcon sx={{ fontSize: 64, mb: 2, color: 'primary.main' }} />
              <Typography variant="h6" gutterBottom>
                Start a conversation
              </Typography>
              <Typography variant="body2">
                Describe the SQL query you need and I'll generate it for you.
              </Typography>
            </Box>
          ) : (
            messages.map((message, index) => (
              <Slide direction="up" in={true} timeout={300 + index * 100} key={message.id}>
                <Box>
                  {/* User Message */}
                  <Box sx={{
                    display: 'flex',
                    gap: 2,
                    mb: 2,
                    justifyContent: 'flex-end'
                  }}>
                    <Box sx={{
                      maxWidth: '70%',
                      backgroundColor: 'primary.main',
                      color: 'white',
                      p: 2,
                      borderRadius: 2,
                      borderTopRightRadius: 0.5,
                    }}>
                      <Typography variant="body1">
                        {message.text}
                      </Typography>
                    </Box>
                    <Avatar sx={{ bgcolor: 'primary.main' }}>
                      <PersonIcon />
                    </Avatar>
                  </Box>

                  {/* AI Response */}
                  {message.sql && (
                    <Box sx={{
                      display: 'flex',
                      gap: 2,
                      mb: 2,
                      justifyContent: 'flex-start'
                    }}>
                      <Avatar sx={{ bgcolor: 'secondary.main' }}>
                        <SmartToyIcon />
                      </Avatar>
                      <Box sx={{
                        maxWidth: '70%',
                        backgroundColor: 'white',
                        p: 2,
                        borderRadius: 2,
                        borderTopLeftRadius: 0.5,
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                        position: 'relative'
                      }}>
                        <Typography variant="body2" sx={{ mb: 1, fontWeight: 500 }}>
                          Generated SQL:
                        </Typography>
                        <Box sx={{ position: 'relative' }}>
                          <SyntaxHighlighter
                            language="sql"
                            style={materialLight}
                            customStyle={{
                              margin: 0,
                              borderRadius: 1,
                              fontSize: '0.875rem'
                            }}
                          >
                            {message.sql}
                          </SyntaxHighlighter>

                          {/* Action Buttons - Only show on last SQL message */}
                          {isLastSqlMessage(index) && (
                            <Stack
                              direction="row"
                              spacing={1}
                              sx={{
                                position: 'absolute',
                                top: 8,
                                right: 8
                              }}
                            >
                              {/* Copy button - always visible */}
                              <Tooltip title="Copy SQL">
                                <IconButton
                                  size="small"
                                  onClick={() => copyToClipboard(message.sql)}
                                  sx={{
                                    backgroundColor: 'rgba(255,255,255,0.9)',
                                    '&:hover': { backgroundColor: 'white' }
                                  }}
                                >
                                  <ContentCopyIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>

                              {/* Show feedback buttons based on feedback_enabled state */}
                              {feedbackEnabled === null && message.correct === null && (
                                <>
                                  <Tooltip title="Correct SQL">
                                    <IconButton
                                      size="small"
                                      color="success"
                                      onClick={() => handleFeedback(message.id, true)}
                                      sx={{
                                        backgroundColor: 'rgba(76,175,80,0.1)',
                                        '&:hover': { backgroundColor: 'rgba(76,175,80,0.2)' }
                                      }}
                                    >
                                      <CheckCircleIcon fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                  <Tooltip title="Incorrect SQL">
                                    <IconButton
                                      size="small"
                                      color="error"
                                      onClick={() => handleFeedback(message.id, false)}
                                      sx={{
                                        backgroundColor: 'rgba(244,67,54,0.1)',
                                        '&:hover': { backgroundColor: 'rgba(244,67,54,0.2)' }
                                      }}
                                    >
                                      <CancelIcon fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                </>
                              )}

                              {/* Show add sample button when feedback is enabled and query is marked correct */}
                              {feedbackEnabled === true && message.correct === true && (
                                <Tooltip title="Add as sample query">
                                  <IconButton
                                    size="small"
                                    color="primary"
                                    onClick={() => handleAddSample(message.id)}
                                    disabled={addingSample === message.id}
                                    sx={{
                                      backgroundColor: 'rgba(25,118,210,0.1)',
                                      '&:hover': { backgroundColor: 'rgba(25,118,210,0.2)' }
                                    }}
                                  >
                                    {addingSample === message.id ? (
                                      <CircularProgress size={16} />
                                    ) : (
                                      <AddCircleIcon fontSize="small" />
                                    )}
                                  </IconButton>
                                </Tooltip>
                              )}
                            </Stack>
                          )}
                        </Box>

                        {/* Feedback Status */}
                        {message.correct !== null && (
                          <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                            <Chip
                              label={message.correct ? "Marked as correct" : "Marked as incorrect"}
                              color={message.correct ? "success" : "error"}
                              size="small"
                            />
                          </Box>
                        )}
                      </Box>
                    </Box>
                  )}

                  {/* Loading Indicator */}
                  {generating && message.id === messages[messages.length - 1].id && !message.sql && (
                    <Box sx={{
                      display: 'flex',
                      gap: 2,
                      mb: 2,
                      justifyContent: 'flex-start'
                    }}>
                      <Avatar sx={{ bgcolor: 'secondary.main' }}>
                        <SmartToyIcon />
                      </Avatar>
                      <Box sx={{
                        backgroundColor: 'white',
                        p: 2,
                        borderRadius: 2,
                        borderTopLeftRadius: 0.5,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1
                      }}>
                        <CircularProgress size={20} />
                        <Typography variant="body2" color="text.secondary">
                          Generating SQL...
                        </Typography>
                      </Box>
                    </Box>
                  )}

                  {index < messages.length - 1 && <Divider sx={{ my: 2 }} />}
                </Box>
              </Slide>
            ))
          )}
          <div ref={messagesEndRef} />
        </CardContent>
      </Card>

      {/* Input Area - Only show when no messages exist */}
      {messages.length === 0 && (
        <Box component="form" onSubmit={handleSubmit} sx={{ mt: 3 }}>
          <TextField
            fullWidth
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe the SQL query you need... (e.g., 'Show me all users who signed up in the last month')"
            multiline
            rows={3}
            sx={{ mb: 2 }}
            disabled={generating}
            variant="outlined"
          />
          <Button
            type="submit"
            variant="contained"
            disabled={!input.trim() || generating}
            size="large"
            sx={{ minWidth: 200 }}
          >
            {generating ? <CircularProgress size={24} /> : 'Generate SQL'}
          </Button>
        </Box>
      )}

      {/* Show info message when chat has messages */}
      {messages.length > 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          {feedbackEnabled === null
            ? "Use the feedback buttons on the SQL query to mark it as correct or incorrect."
            : feedbackEnabled === true
              ? "Mark the query as correct to add it as a sample query."
              : "Feedback completed. No further actions available."
          }
        </Alert>
      )}

      {/* Feedback Confirmation */}
      <Fade in={feedbackSubmitted}>
        <Alert severity="success" sx={{ position: 'fixed', bottom: 20, right: 20, zIndex: 1000 }}>
          Feedback submitted successfully!
        </Alert>
      </Fade>

      {/* Copy Confirmation */}
      <Fade in={copied}>
        <Alert severity="success" sx={{ position: 'fixed', bottom: 20, right: 20, zIndex: 1000 }}>
          SQL copied to clipboard!
        </Alert>
      </Fade>

      {/* Sample Added Confirmation */}
      <Fade in={sampleAdded}>
        <Alert severity="success" sx={{ position: 'fixed', bottom: 20, right: 20, zIndex: 1000 }}>
          Sample query added successfully!
        </Alert>
      </Fade>
    </Box>
  );
}

export default ChatDetail;