import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import Layout from './components/Layout';
import ProjectList from './pages/ProjectList';
import NewProject from './pages/NewProject';
import ProjectDetail from './pages/ProjectDetail';
import ChatList from './pages/ChatList';
import ChatDetail from './pages/ChatDetail';
import ApiErrorBoundary from './components/ApiErrorBoundary';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        },
      },
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        width: '100vw',
        margin: 0,
        padding: 0,
      }}>
        <ApiErrorBoundary>
          {(handleError) => (
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<Layout />}>
                  <Route index element={<ProjectList onError={handleError} />} />
                  <Route path="new-project" element={<NewProject onError={handleError} />} />
                  <Route path="project/:projectId">
                    <Route index element={<ProjectDetail onError={handleError} />} />
                    <Route path="chat" element={<ChatList onError={handleError} />} />
                    <Route path="chat/:chatId" element={<ChatDetail onError={handleError} />} />
                  </Route>
                </Route>
              </Routes>
            </BrowserRouter>
          )}
        </ApiErrorBoundary>
      </div>
    </ThemeProvider>
  );
}

export default App;
