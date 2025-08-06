import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemText,
  Button,
  CircularProgress,
  Card,
  CardContent,
  Avatar,
  Chip,
  Divider,
} from '@mui/material';
import ChatIcon from '@mui/icons-material/Chat';
import AddIcon from '@mui/icons-material/Add';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { projectApi, chatApi } from '../services/api';

function ChatList({ onError }) {
  const navigate = useNavigate();
  const { projectId } = useParams();
  const [allChats, setAllChats] = useState([]);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProjectAndChats();
  }, [projectId]);

  const loadProjectAndChats = async () => {
    try {
      const projectData = await projectApi.getProject(projectId);
      setProject(projectData);

      const chatsData = await chatApi.getChats(projectId);
      setAllChats(chatsData);
    } catch (err) {
      onError(err);
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = async () => {
    try {
      const newChat = await chatApi.createChat(projectId);
      setAllChats(prev => [...prev, newChat]);
      navigate(`/project/${projectId}/chat/${newChat.id}`);
    } catch (err) {
      onError(err);
    }
  };

  if (loading) {
    return (
      <Box sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '60vh'
      }}>
        <CircularProgress size={48} />
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%' }}>
      {/* Header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        mb: 3,
        flexWrap: 'wrap'
      }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/')}
          variant="outlined"
          size="small"
        >
          Back to Projects
        </Button>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.5 }}>
            {project?.name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage your chat conversations
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleNewChat}
          sx={{
            minWidth: 'fit-content',
            px: 3
          }}
        >
          New Chat
        </Button>
      </Box>

      {/* Chat List */}
      <Card sx={{
        borderRadius: 2,
        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        overflow: 'hidden'
      }}>
        <CardContent sx={{ p: 0 }}>
          {allChats.length === 0 ? (
            <Box sx={{
              textAlign: 'center',
              py: 6,
              px: 3
            }}>
              <ChatIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
              <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>
                No chats yet
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Start your first conversation to generate SQL queries
              </Typography>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={handleNewChat}
              >
                Start New Chat
              </Button>
            </Box>
          ) : (
            <List sx={{ p: 0 }}>
              {allChats.map((chat, index) => (
                <Box key={chat.id}>
                  <ListItem
                    button
                    onClick={() => navigate(`/project/${projectId}/chat/${chat.id}`)}
                    sx={{
                      p: 3,
                      transition: 'background-color 0.2s',
                      '&:hover': {
                        backgroundColor: 'rgba(25,118,210,0.04)'
                      }
                    }}
                  >
                    <Avatar sx={{
                      bgcolor: 'primary.main',
                      mr: 2,
                      width: 40,
                      height: 40
                    }}>
                      <ChatIcon />
                    </Avatar>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="h6" sx={{ fontWeight: 500, mb: 1 }}>
                        Chat {chat.id}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        {chat.query_history?.[0]?.text || 'Empty chat'}
                      </Typography>
                      <Chip
                        label={`${chat.query_history?.length || 0} messages`}
                        size="small"
                        variant="outlined"
                        color="primary"
                      />
                    </Box>
                  </ListItem>
                  {index < allChats.length - 1 && <Divider />}
                </Box>
              ))}
            </List>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}

export default ChatList;