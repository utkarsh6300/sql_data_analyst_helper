import React, { useState } from 'react';
import { Alert, Snackbar } from '@mui/material';

function ApiErrorBoundary({ children }) {
  const [error, setError] = useState(null);

  const handleError = (error) => {
    setError(error);
    // You can also log the error to an error reporting service here
    console.error('API Error:', error);
  };

  const handleClose = () => {
    setError(null);
  };

  return (
    <>
      {children(handleError)}
      <Snackbar 
        open={!!error} 
        autoHideDuration={6000} 
        onClose={handleClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleClose} severity="error" sx={{ width: '100%' }}>
          {error?.message || 'An error occurred. Please try again.'}
        </Alert>
      </Snackbar>
    </>
  );
}

export default ApiErrorBoundary;