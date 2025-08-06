import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    Box,
    Card,
    CardContent,
    Typography,
    Button,
    Grid,
    CircularProgress,
    Chip,
    Avatar,
    Tabs,
    Tab,
    TextField,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    IconButton,
    List,
    ListItem,
    ListItemText,
    ListItemSecondaryAction,
    Divider,
    Alert,
    Paper,
} from '@mui/material';
import {
    Folder as FolderIcon,
    Chat as ChatIcon,
    Add as AddIcon,
    Delete as DeleteIcon,
    Edit as EditIcon,
    Code as CodeIcon,
    Description as DescriptionIcon,
    QuestionAnswer as QuestionAnswerIcon,
} from '@mui/icons-material';
import { projectApi } from '../services/api';

function TabPanel({ children, value, index, ...other }) {
    return (
        <div
            role="tabpanel"
            hidden={value !== index}
            id={`project-tabpanel-${index}`}
            aria-labelledby={`project-tab-${index}`}
            {...other}
        >
            {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
        </div>
    );
}

function ProjectDetail({ onError }) {
    const { projectId } = useParams();
    const navigate = useNavigate();
    const [project, setProject] = useState(null);
    const [loading, setLoading] = useState(true);
    const [tabValue, setTabValue] = useState(0);
    const [addDialogOpen, setAddDialogOpen] = useState(false);
    const [addDialogType, setAddDialogType] = useState('');
    const [newItem, setNewItem] = useState({});
    const [successMessage, setSuccessMessage] = useState('');

    useEffect(() => {
        loadProject();
    }, [projectId]);

    const loadProject = async () => {
        try {
            setLoading(true);
            const data = await projectApi.getProject(projectId);
            setProject(data);
        } catch (err) {
            console.error('Error loading project:', err);
            onError(err);
        } finally {
            setLoading(false);
        }
    };

    const handleTabChange = (event, newValue) => {
        setTabValue(newValue);
    };

    const openAddDialog = (type) => {
        setAddDialogType(type);
        setNewItem({});
        setAddDialogOpen(true);
    };

    const closeAddDialog = () => {
        setAddDialogOpen(false);
        setNewItem({});
    };

    const handleAddItem = async () => {
        try {
            let response;
            switch (addDialogType) {
                case 'ddl':
                    response = await projectApi.addDdlStatements(projectId, [{ ddl: newItem.ddl }]);
                    break;
                case 'documentation':
                    response = await projectApi.addDocumentationItems(projectId, [{ documentation: newItem.documentation }]);
                    break;
                case 'sql':
                    response = await projectApi.addQuestionSqlPairs(projectId, [{
                        question: newItem.question,
                        sql: newItem.sql
                    }]);
                    break;
                default:
                    return;
            }

            setSuccessMessage(`${addDialogType.toUpperCase()} item added successfully!`);
            closeAddDialog();
            await loadProject(); // Reload project data

            // Clear success message after 3 seconds
            setTimeout(() => setSuccessMessage(''), 3000);
        } catch (err) {
            console.error('Error adding item:', err);
            onError(err);
        }
    };

    const handleDeleteItem = async (type, itemId) => {
        try {
            let response;
            switch (type) {
                case 'ddl':
                    response = await projectApi.deleteDdlItem(itemId);
                    break;
                case 'documentation':
                    response = await projectApi.deleteDocumentationItem(itemId);
                    break;
                case 'sql':
                    response = await projectApi.deleteQuestionSqlItem(itemId);
                    break;
                default:
                    return;
            }

            setSuccessMessage(`${type.toUpperCase()} item deleted successfully!`);
            await loadProject(); // Reload project data

            // Clear success message after 3 seconds
            setTimeout(() => setSuccessMessage(''), 3000);
        } catch (err) {
            console.error('Error deleting item:', err);
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

    if (!project) {
        return (
            <Box sx={{ textAlign: 'center', py: 8 }}>
                <Typography variant="h6" color="text.secondary">
                    Project not found
                </Typography>
            </Box>
        );
    }

    return (
        <Box sx={{ width: '100%' }}>
            {successMessage && (
                <Alert severity="success" sx={{ mb: 2 }}>
                    {successMessage}
                </Alert>
            )}

            {/* Project Header */}
            <Card sx={{ mb: 3 }}>
                <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <Avatar sx={{
                            bgcolor: 'primary.main',
                            mr: 2,
                            width: 56,
                            height: 56
                        }}>
                            <FolderIcon />
                        </Avatar>
                        <Box sx={{ flex: 1 }}>
                            <Typography variant="h4" sx={{ fontWeight: 600, mb: 1 }}>
                                {project.name}
                            </Typography>
                            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                                <Chip
                                    label={`${project.chatsCount || 0} chats`}
                                    color="primary"
                                    variant="outlined"
                                />
                                <Typography variant="body2" color="text.secondary">
                                    Created: {new Date(project.created_at).toLocaleDateString()}
                                </Typography>
                            </Box>
                        </Box>
                        <Button
                            variant="contained"
                            startIcon={<ChatIcon />}
                            onClick={() => navigate(`/project/${projectId}/chat`)}
                            sx={{ ml: 2 }}
                        >
                            Open Chat
                        </Button>
                    </Box>
                </CardContent>
            </Card>

            {/* Tabs */}
            <Paper sx={{ width: '100%' }}>
                <Tabs value={tabValue} onChange={handleTabChange} aria-label="project tabs">
                    <Tab
                        icon={<CodeIcon />}
                        label="DDL Statements"
                        iconPosition="start"
                    />
                    <Tab
                        icon={<DescriptionIcon />}
                        label="Documentation"
                        iconPosition="start"
                    />
                    <Tab
                        icon={<QuestionAnswerIcon />}
                        label="Question-SQL Pairs"
                        iconPosition="start"
                    />
                </Tabs>

                {/* DDL Statements Tab */}
                <TabPanel value={tabValue} index={0}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">DDL Statements</Typography>
                        <Button
                            variant="contained"
                            startIcon={<AddIcon />}
                            onClick={() => openAddDialog('ddl')}
                        >
                            Add DDL
                        </Button>
                    </Box>

                    {project.ddl_statements && project.ddl_statements.length > 0 ? (
                        <List>
                            {project.ddl_statements.map((item, index) => (
                                <Box key={item.id || index}>
                                    <ListItem>
                                        <ListItemText
                                            primary={
                                                <Typography variant="body1" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                    {item.ddl}
                                                </Typography>
                                            }
                                        />
                                        <ListItemSecondaryAction>
                                            <IconButton
                                                edge="end"
                                                onClick={() => handleDeleteItem('ddl', item.id)}
                                                color="error"
                                            >
                                                <DeleteIcon />
                                            </IconButton>
                                        </ListItemSecondaryAction>
                                    </ListItem>
                                    {index < project.ddl_statements.length - 1 && <Divider />}
                                </Box>
                            ))}
                        </List>
                    ) : (
                        <Box sx={{ textAlign: 'center', py: 4 }}>
                            <CodeIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                            <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>
                                No DDL statements
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Add DDL statements to help with SQL generation
                            </Typography>
                        </Box>
                    )}
                </TabPanel>

                {/* Documentation Tab */}
                <TabPanel value={tabValue} index={1}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">Documentation</Typography>
                        <Button
                            variant="contained"
                            startIcon={<AddIcon />}
                            onClick={() => openAddDialog('documentation')}
                        >
                            Add Documentation
                        </Button>
                    </Box>

                    {project.documentation_items && project.documentation_items.length > 0 ? (
                        <List>
                            {project.documentation_items.map((item, index) => (
                                <Box key={item.id || index}>
                                    <ListItem>
                                        <ListItemText
                                            primary={
                                                <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
                                                    {item.documentation}
                                                </Typography>
                                            }
                                        />
                                        <ListItemSecondaryAction>
                                            <IconButton
                                                edge="end"
                                                onClick={() => handleDeleteItem('documentation', item.id)}
                                                color="error"
                                            >
                                                <DeleteIcon />
                                            </IconButton>
                                        </ListItemSecondaryAction>
                                    </ListItem>
                                    {index < project.documentation_items.length - 1 && <Divider />}
                                </Box>
                            ))}
                        </List>
                    ) : (
                        <Box sx={{ textAlign: 'center', py: 4 }}>
                            <DescriptionIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                            <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>
                                No documentation
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Add documentation to help with SQL generation
                            </Typography>
                        </Box>
                    )}
                </TabPanel>

                {/* Question-SQL Pairs Tab */}
                <TabPanel value={tabValue} index={2}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">Question-SQL Pairs</Typography>
                        <Button
                            variant="contained"
                            startIcon={<AddIcon />}
                            onClick={() => openAddDialog('sql')}
                        >
                            Add Question-SQL Pair
                        </Button>
                    </Box>

                    {project.question_sql_pairs && project.question_sql_pairs.length > 0 ? (
                        <List>
                            {project.question_sql_pairs.map((item, index) => (
                                <Box key={item.id || index}>
                                    <ListItem>
                                        <ListItemText
                                            primary={
                                                <Box>
                                                    <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                                                        Question:
                                                    </Typography>
                                                    <Typography variant="body1" sx={{ mb: 2 }}>
                                                        {item.question}
                                                    </Typography>
                                                    <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                                                        SQL:
                                                    </Typography>
                                                    <Typography variant="body1" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                        {item.sql}
                                                    </Typography>
                                                </Box>
                                            }
                                        />
                                        <ListItemSecondaryAction>
                                            <IconButton
                                                edge="end"
                                                onClick={() => handleDeleteItem('sql', item.id)}
                                                color="error"
                                            >
                                                <DeleteIcon />
                                            </IconButton>
                                        </ListItemSecondaryAction>
                                    </ListItem>
                                    {index < project.question_sql_pairs.length - 1 && <Divider />}
                                </Box>
                            ))}
                        </List>
                    ) : (
                        <Box sx={{ textAlign: 'center', py: 4 }}>
                            <QuestionAnswerIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                            <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>
                                No question-SQL pairs
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                Add question-SQL pairs to help with SQL generation
                            </Typography>
                        </Box>
                    )}
                </TabPanel>
            </Paper>

            {/* Add Item Dialog */}
            <Dialog open={addDialogOpen} onClose={closeAddDialog} maxWidth="md" fullWidth>
                <DialogTitle>
                    Add {addDialogType === 'ddl' ? 'DDL Statement' :
                        addDialogType === 'documentation' ? 'Documentation' :
                            'Question-SQL Pair'}
                </DialogTitle>
                <DialogContent>
                    {addDialogType === 'ddl' && (
                        <TextField
                            autoFocus
                            margin="dense"
                            label="DDL Statement"
                            type="text"
                            fullWidth
                            multiline
                            rows={6}
                            value={newItem.ddl || ''}
                            onChange={(e) => setNewItem({ ...newItem, ddl: e.target.value })}
                            placeholder="Enter your DDL statement here..."
                        />
                    )}

                    {addDialogType === 'documentation' && (
                        <TextField
                            autoFocus
                            margin="dense"
                            label="Documentation"
                            type="text"
                            fullWidth
                            multiline
                            rows={6}
                            value={newItem.documentation || ''}
                            onChange={(e) => setNewItem({ ...newItem, documentation: e.target.value })}
                            placeholder="Enter your documentation here..."
                        />
                    )}

                    {addDialogType === 'sql' && (
                        <Box>
                            <TextField
                                autoFocus
                                margin="dense"
                                label="Question"
                                type="text"
                                fullWidth
                                multiline
                                rows={3}
                                value={newItem.question || ''}
                                onChange={(e) => setNewItem({ ...newItem, question: e.target.value })}
                                placeholder="Enter your question here..."
                                sx={{ mb: 2 }}
                            />
                            <TextField
                                margin="dense"
                                label="SQL Query"
                                type="text"
                                fullWidth
                                multiline
                                rows={6}
                                value={newItem.sql || ''}
                                onChange={(e) => setNewItem({ ...newItem, sql: e.target.value })}
                                placeholder="Enter your SQL query here..."
                            />
                        </Box>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={closeAddDialog}>Cancel</Button>
                    <Button
                        onClick={handleAddItem}
                        variant="contained"
                        disabled={
                            (addDialogType === 'ddl' && !newItem.ddl) ||
                            (addDialogType === 'documentation' && !newItem.documentation) ||
                            (addDialogType === 'sql' && (!newItem.question || !newItem.sql))
                        }
                    >
                        Add
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
}

export default ProjectDetail; 