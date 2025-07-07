import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Stepper,
  Step,
  StepLabel,
  Button,
  Typography,
  Paper,
  TextField,
  CircularProgress,
  Alert
} from '@mui/material';
import { projectApi } from '../services/api';

const steps = ['Add Database Schema', 'Add Documentation', 'Add Sample Queries'];

const validateStep = (step, data) => {
  switch (step) {
    case 0:
      return {
        isValid: data.name.trim() !== '' && data.schema.trim() !== '',
        errors: {
          name: data.name.trim() === '' ? 'Project name is required' : '',
          schema: data.schema.trim() === '' ? 'Database schema is required' : ''
        }
      };
    case 1:
      return {
        isValid: data.documentation.trim() !== '',
        errors: {
          documentation: data.documentation.trim() === '' ? 'Documentation is required' : ''
        }
      };
    case 2:
      return {
        isValid: data.sampleQueries.some(q => q.text.trim() !== '' && q.sql.trim() !== ''),
        errors: {
          sampleQueries: data.sampleQueries.every(q => q.text.trim() === '' || q.sql.trim() === '')
            ? 'At least one sample query is required'
            : ''
        }
      };
    default:
      return { isValid: true, errors: {} };
  }
};

function NewProject({ onError }) {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [validation, setValidation] = useState({ isValid: true, errors: {} });
  const [projectData, setProjectData] = useState({
    name: '',
    schema: '',
    documentation: '',
    sampleQueries: [{ text: '', sql: '' }]
  });

  const handleNext = () => {
    const stepValidation = validateStep(activeStep, projectData);
    setValidation(stepValidation);

    if (stepValidation.isValid) {
      setActiveStep((prevStep) => prevStep + 1);
    }
  };

  const handleBack = () => {
    setActiveStep((prevStep) => prevStep - 1);
    setValidation({ isValid: true, errors: {} });
  };

  const handleCreate = async () => {
    const stepValidation = validateStep(activeStep, projectData);
    setValidation(stepValidation);

    if (!stepValidation.isValid) {
      return;
    }

    setLoading(true);
    try {
      // Step 1: Create the project with name and schema
      const project = await projectApi.createProject({
        name: projectData.name,
        schema: projectData.schema
      });

      // Step 2: Add schema to vector store
      await projectApi.addSchema(project.id, {
        schema: projectData.schema
      });

      // Step 3: Add documentation
      if (projectData.documentation.trim()) {
        await projectApi.addDocumentation(project.id, {
          documentation: projectData.documentation
        });
      }

      // Step 4: Add sample queries
      const validQueries = projectData.sampleQueries.filter(q => q.text.trim() !== '' && q.sql.trim() !== '');
      if (validQueries.length > 0) {
        const sampleQueries = {};
        validQueries.forEach(query => {
          sampleQueries[query.text] = query.sql;
        });

        await projectApi.addSampleQueries(project.id, {
          sample_queries: sampleQueries
        });
      }

      navigate('/');
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSampleQueryChange = (index, field, value) => {
    const newQueries = [...projectData.sampleQueries];
    newQueries[index] = { ...newQueries[index], [field]: value };
    setProjectData({ ...projectData, sampleQueries: newQueries });
    setValidation({ isValid: true, errors: {} });
  };

  const addSampleQuery = () => {
    setProjectData({
      ...projectData,
      sampleQueries: [...projectData.sampleQueries, { text: '', sql: '' }]
    });
  };

  const getStepContent = (step) => {
    switch (step) {
      case 0:
        return (
          <Box sx={{ mt: 2 }}>
            <TextField
              fullWidth
              label="Project Name"
              value={projectData.name}
              onChange={(e) => {
                setProjectData({ ...projectData, name: e.target.value });
                setValidation({ isValid: true, errors: {} });
              }}
              error={!!validation.errors.name}
              helperText={validation.errors.name}
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth
              label="Database Schema"
              multiline
              rows={10}
              value={projectData.schema}
              onChange={(e) => {
                setProjectData({ ...projectData, schema: e.target.value });
                setValidation({ isValid: true, errors: {} });
              }}
              error={!!validation.errors.schema}
              helperText={validation.errors.schema}
              placeholder="Enter your database schema (SQL CREATE TABLE statements)"
            />
          </Box>
        );
      case 1:
        return (
          <TextField
            fullWidth
            label="Documentation"
            multiline
            rows={10}
            value={projectData.documentation}
            onChange={(e) => {
              setProjectData({ ...projectData, documentation: e.target.value });
              setValidation({ isValid: true, errors: {} });
            }}
            error={!!validation.errors.documentation}
            helperText={validation.errors.documentation}
            placeholder="Enter documentation about your database schema, tables, and their relationships"
            sx={{ mt: 2 }}
          />
        );
      case 2:
        return (
          <Box sx={{ mt: 2 }}>
            {validation.errors.sampleQueries && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {validation.errors.sampleQueries}
              </Alert>
            )}
            {projectData.sampleQueries.map((query, index) => (
              <Paper key={index} sx={{ p: 2, mb: 2 }}>
                <TextField
                  fullWidth
                  label="Natural Language Query"
                  value={query.text}
                  onChange={(e) => handleSampleQueryChange(index, 'text', e.target.value)}
                  sx={{ mb: 2 }}
                />
                <TextField
                  fullWidth
                  label="SQL Query"
                  multiline
                  rows={4}
                  value={query.sql}
                  onChange={(e) => handleSampleQueryChange(index, 'sql', e.target.value)}
                />
              </Paper>
            ))}
            <Button onClick={addSampleQuery}>Add Another Query</Button>
          </Box>
        );
      default:
        return 'Unknown step';
    }
  };

  return (
    <Box sx={{ width: '100%', maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h4" sx={{ mb: 4 }}>Create New Project</Typography>

      <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {getStepContent(activeStep)}

      <Box sx={{ display: 'flex', flexDirection: 'row', pt: 2 }}>
        <Button
          color="inherit"
          disabled={activeStep === 0 || loading}
          onClick={handleBack}
          sx={{ mr: 1 }}
        >
          Back
        </Button>
        <Box sx={{ flex: '1 1 auto' }} />
        <Button
          onClick={activeStep === steps.length - 1 ? handleCreate : handleNext}
          disabled={loading}
          variant="contained"
        >
          {loading ? (
            <CircularProgress size={24} />
          ) : (
            activeStep === steps.length - 1 ? 'Create Project' : 'Next'
          )}
        </Button>
      </Box>
    </Box>
  );
}

export default NewProject;