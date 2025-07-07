import { Outlet, useNavigate } from 'react-router-dom';
import { AppBar, Toolbar, Typography, Button, Box } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';

function Layout() {
  const navigate = useNavigate();

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      minHeight: '100vh',
      width: '100vw'
    }}>
      <AppBar position="static" elevation={1}>
        <Toolbar sx={{ px: { xs: 2, sm: 3, md: 4 } }}>
          <Typography
            variant="h6"
            component="div"
            sx={{
              flexGrow: 1,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: { xs: '1.1rem', sm: '1.25rem' }
            }}
            onClick={() => navigate('/')}
          >
            Text to SQL Generator
          </Typography>
          <Button
            color="inherit"
            startIcon={<AddIcon />}
            onClick={() => navigate('/new-project')}
            variant="outlined"
            sx={{
              borderColor: 'rgba(255,255,255,0.3)',
              '&:hover': { borderColor: 'rgba(255,255,255,0.5)' }
            }}
          >
            New Project
          </Button>
        </Toolbar>
      </AppBar>
      <Box sx={{
        display: 'flex',
        flexDirection: 'column',
        flexGrow: 1,
        width: '100vw'
      }}>
        <Box sx={{
          py: 3,
          px: { xs: 2, sm: 3, md: 4 },
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          flex: 1
        }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}

export default Layout;