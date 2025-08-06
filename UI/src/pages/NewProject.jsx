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
  Alert,
  IconButton,
  Divider
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import { projectApi } from '../services/api';

const steps = ['Add Database Schema (DDL)', 'Add Documentation', 'Add Sample Queries'];

const validateStep = (step, data) => {
  switch (step) {
    case 0:
      return {
        isValid: data.name.trim() !== '' && data.ddlStatements.length > 0 && data.ddlStatements.every(ddl => ddl.ddl.trim() !== ''),
        errors: {
          name: data.name.trim() === '' ? 'Project name is required' : '',
          ddlStatements: data.ddlStatements.length === 0 || data.ddlStatements.every(ddl => ddl.ddl.trim() === '')
            ? 'At least one DDL statement is required' : ''
        }
      };
    case 1:
      return {
        isValid: data.documentationItems.length > 0 && data.documentationItems.every(doc => doc.documentation.trim() !== ''),
        errors: {
          documentationItems: data.documentationItems.length === 0 || data.documentationItems.every(doc => doc.documentation.trim() === '')
            ? 'At least one documentation item is required' : ''
        }
      };
    case 2:
      return {
        isValid: data.questionSqlPairs.length > 0 && data.questionSqlPairs.every(pair => pair.question.trim() !== '' && pair.sql.trim() !== ''),
        errors: {
          questionSqlPairs: data.questionSqlPairs.length === 0 || data.questionSqlPairs.every(pair => pair.question.trim() === '' || pair.sql.trim() === '')
            ? 'At least one question-SQL pair is required' : ''
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
    ddlStatements: [{ ddl: '', metadata: {} }],
    documentationItems: [{ documentation: '', metadata: {} }],
    questionSqlPairs: [{ question: '', sql: '', metadata: {} }]
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
      // Step 1: Create the project with name
      const project = await projectApi.createProject({
        name: projectData.name
      });

      // Step 2: Add DDL statements
      const validDdlStatements = projectData.ddlStatements.filter(ddl => ddl.ddl.trim() !== '');
      if (validDdlStatements.length > 0) {
        await projectApi.addDdlStatements(project.id, validDdlStatements);
      }

      // Step 3: Add documentation items
      const validDocumentationItems = projectData.documentationItems.filter(doc => doc.documentation.trim() !== '');
      if (validDocumentationItems.length > 0) {
        await projectApi.addDocumentationItems(project.id, validDocumentationItems);
      }

      // Step 4: Add question-SQL pairs
      const validQuestionSqlPairs = projectData.questionSqlPairs.filter(pair => pair.question.trim() !== '' && pair.sql.trim() !== '');
      if (validQuestionSqlPairs.length > 0) {
        await projectApi.addQuestionSqlPairs(project.id, validQuestionSqlPairs);
      }

      navigate('/');
    } catch (error) {
      onError(error);
    } finally {
      setLoading(false);
    }
  };

  const handleDdlChange = (index, field, value) => {
    const newDdlStatements = [...projectData.ddlStatements];
    newDdlStatements[index] = { ...newDdlStatements[index], [field]: value };
    setProjectData({ ...projectData, ddlStatements: newDdlStatements });
    setValidation({ isValid: true, errors: {} });
  };

  const addDdlStatement = () => {
    setProjectData({
      ...projectData,
      ddlStatements: [...projectData.ddlStatements, { ddl: '', metadata: {} }]
    });
  };

  const removeDdlStatement = (index) => {
    const newDdlStatements = projectData.ddlStatements.filter((_, i) => i !== index);
    setProjectData({ ...projectData, ddlStatements: newDdlStatements });
  };

  const handleDocumentationChange = (index, field, value) => {
    const newDocumentationItems = [...projectData.documentationItems];
    newDocumentationItems[index] = { ...newDocumentationItems[index], [field]: value };
    setProjectData({ ...projectData, documentationItems: newDocumentationItems });
    setValidation({ isValid: true, errors: {} });
  };

  const addDocumentationItem = () => {
    setProjectData({
      ...projectData,
      documentationItems: [...projectData.documentationItems, { documentation: '', metadata: {} }]
    });
  };

  const removeDocumentationItem = (index) => {
    const newDocumentationItems = projectData.documentationItems.filter((_, i) => i !== index);
    setProjectData({ ...projectData, documentationItems: newDocumentationItems });
  };

  const handleQuestionSqlChange = (index, field, value) => {
    const newQuestionSqlPairs = [...projectData.questionSqlPairs];
    newQuestionSqlPairs[index] = { ...newQuestionSqlPairs[index], [field]: value };
    setProjectData({ ...projectData, questionSqlPairs: newQuestionSqlPairs });
    setValidation({ isValid: true, errors: {} });
  };

  const addQuestionSqlPair = () => {
    setProjectData({
      ...projectData,
      questionSqlPairs: [...projectData.questionSqlPairs, { question: '', sql: '', metadata: {} }]
    });
  };

  const removeQuestionSqlPair = (index) => {
    const newQuestionSqlPairs = projectData.questionSqlPairs.filter((_, i) => i !== index);
    setProjectData({ ...projectData, questionSqlPairs: newQuestionSqlPairs });
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
              sx={{ mb: 3 }}
            />

            {validation.errors.ddlStatements && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {validation.errors.ddlStatements}
              </Alert>
            )}

            <Typography variant="h6" sx={{ mb: 2 }}>Database Schema (DDL Statements)</Typography>
            {projectData.ddlStatements.map((ddl, index) => (
              <Paper key={index} sx={{ p: 2, mb: 2, position: 'relative' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                  <Typography variant="subtitle2">DDL Statement {index + 1}</Typography>
                  {projectData.ddlStatements.length > 1 && (
                    <IconButton
                      size="small"
                      onClick={() => removeDdlStatement(index)}
                      color="error"
                    >
                      <DeleteIcon />
                    </IconButton>
                  )}
                </Box>
                <TextField
                  fullWidth
                  label="DDL Statement"
                  multiline
                  rows={4}
                  value={ddl.ddl}
                  onChange={(e) => handleDdlChange(index, 'ddl', e.target.value)}
                  placeholder="CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(255), email VARCHAR(255));"
                />
              </Paper>
            ))}
            <Button onClick={addDdlStatement} variant="outlined" sx={{ mt: 1 }}>
              Add Another DDL Statement
            </Button>
          </Box>
        );
      case 1:
        return (
          <Box sx={{ mt: 2 }}>
            {validation.errors.documentationItems && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {validation.errors.documentationItems}
              </Alert>
            )}

            <Typography variant="h6" sx={{ mb: 2 }}>Documentation Items</Typography>
            {projectData.documentationItems.map((doc, index) => (
              <Paper key={index} sx={{ p: 2, mb: 2, position: 'relative' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                  <Typography variant="subtitle2">Documentation Item {index + 1}</Typography>
                  {projectData.documentationItems.length > 1 && (
                    <IconButton
                      size="small"
                      onClick={() => removeDocumentationItem(index)}
                      color="error"
                    >
                      <DeleteIcon />
                    </IconButton>
                  )}
                </Box>
                <TextField
                  fullWidth
                  label="Documentation"
                  multiline
                  rows={6}
                  value={doc.documentation}
                  onChange={(e) => handleDocumentationChange(index, 'documentation', e.target.value)}
                  placeholder="Describe the database schema, table relationships, business rules, and any important context..."
                />
              </Paper>
            ))}
            <Button onClick={addDocumentationItem} variant="outlined" sx={{ mt: 1 }}>
              Add Another Documentation Item
            </Button>
          </Box>
        );
      case 2:
        return (
          <Box sx={{ mt: 2 }}>
            {validation.errors.questionSqlPairs && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {validation.errors.questionSqlPairs}
              </Alert>
            )}

            <Typography variant="h6" sx={{ mb: 2 }}>Sample Question-SQL Pairs</Typography>
            {projectData.questionSqlPairs.map((pair, index) => (
              <Paper key={index} sx={{ p: 2, mb: 2, position: 'relative' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                  <Typography variant="subtitle2">Question-SQL Pair {index + 1}</Typography>
                  {projectData.questionSqlPairs.length > 1 && (
                    <IconButton
                      size="small"
                      onClick={() => removeQuestionSqlPair(index)}
                      color="error"
                    >
                      <DeleteIcon />
                    </IconButton>
                  )}
                </Box>
                <TextField
                  fullWidth
                  label="Natural Language Question"
                  value={pair.question}
                  onChange={(e) => handleQuestionSqlChange(index, 'question', e.target.value)}
                  sx={{ mb: 2 }}
                  placeholder="e.g., Show me all users who signed up in the last month"
                />
                <TextField
                  fullWidth
                  label="SQL Query"
                  multiline
                  rows={4}
                  value={pair.sql}
                  onChange={(e) => handleQuestionSqlChange(index, 'sql', e.target.value)}
                  placeholder="SELECT * FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH);"
                />
              </Paper>
            ))}
            <Button onClick={addQuestionSqlPair} variant="outlined" sx={{ mt: 1 }}>
              Add Another Question-SQL Pair
            </Button>
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