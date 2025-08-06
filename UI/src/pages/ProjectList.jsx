import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
  Grid,
  CircularProgress,
  Chip,
  Avatar,
} from '@mui/material';
import ChatIcon from '@mui/icons-material/Chat';
import FolderIcon from '@mui/icons-material/Folder';
import { projectApi } from '../services/api';

function ProjectList({ onError }) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      const data = await projectApi.getProjects();
      setProjects(data);
    } catch (err) {
      onError(err);
    } finally {
      setLoading(false);
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
      <Box sx={{
        textAlign: 'center',
        mb: 4,
        px: { xs: 2, sm: 0 }
      }}>
        <Typography
          variant="h4"
          sx={{
            mb: 2,
            fontWeight: 600,
            color: 'text.primary'
          }}
        >
          Your Projects
        </Typography>
        <Typography
          variant="body1"
          color="text.secondary"
          sx={{ maxWidth: 600, mx: 'auto' }}
        >
          Manage your SQL generation projects and start new conversations
        </Typography>
      </Box>

      {projects.length === 0 ? (
        <Box sx={{
          textAlign: 'center',
          py: 8,
          px: { xs: 2, sm: 0 }
        }}>
          <FolderIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
          <Typography
            variant="h6"
            color="text.secondary"
            sx={{ mb: 1 }}
          >
            No projects yet
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 3 }}
          >
            Create your first project to start generating SQL queries
          </Typography>
          <Button
            variant="contained"
            size="large"
            onClick={() => navigate('/new-project')}
            startIcon={<ChatIcon />}
          >
            Create New Project
          </Button>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {projects.map((project) => (
            <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={project.id}>
              <Card sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                transition: 'transform 0.2s, box-shadow 0.2s',
                '&:hover': {
                  transform: 'translateY(-2px)',
                  boxShadow: '0 8px 25px rgba(0,0,0,0.15)',
                }
              }}>
                <CardContent sx={{ flex: 1, p: 3 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Avatar sx={{
                      bgcolor: 'primary.main',
                      mr: 2,
                      width: 40,
                      height: 40
                    }}>
                      <FolderIcon />
                    </Avatar>
                    <Box sx={{ flex: 1 }}>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 600,
                          mb: 0.5,
                          lineHeight: 1.2
                        }}
                      >
                        {project.name}
                      </Typography>
                      <Chip
                        label={`${project.chatsCount || 0} chats`}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </Box>
                  </Box>

                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                      lineHeight: 1.5,
                      mb: 2
                    }}
                  >
                    {project.description || 'SQL generation project'}
                  </Typography>
                </CardContent>

                <CardActions sx={{ p: 3, pt: 0 }}>
                  <Button
                    fullWidth
                    variant="outlined"
                    startIcon={<FolderIcon />}
                    onClick={() => navigate(`/project/${project.id}`)}
                    sx={{
                      py: 1.5,
                      fontWeight: 500,
                      mb: 1
                    }}
                  >
                    View Details
                  </Button>
                  <Button
                    fullWidth
                    variant="contained"
                    startIcon={<ChatIcon />}
                    onClick={() => navigate(`/project/${project.id}/chat`)}
                    sx={{
                      py: 1.5,
                      fontWeight: 500
                    }}
                  >
                    Open Chat
                  </Button>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}

export default ProjectList;