# Analyst Helper UI

A React-based frontend for the Analyst Helper application that provides SQL generation capabilities with project management.

## Features

### Project Management
- **Project List**: View all your SQL generation projects
- **Project Details**: Comprehensive view of project information with tabs for:
  - DDL Statements: Add, view, and delete database schema definitions
  - Documentation: Add, view, and delete project documentation
  - Question-SQL Pairs: Add, view, and delete example question-SQL mappings
- **New Project Creation**: Create new projects for SQL generation

### Chat Interface
- **Chat List**: View all chats within a project
- **Chat Detail**: Interactive chat interface for SQL generation
- **Real-time Feedback**: Provide feedback on generated SQL queries

## Getting Started

### Prerequisites
- Node.js (v16 or higher)
- npm or yarn

### Installation
1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. The application will be available at `http://localhost:5173`

### Backend Requirements
Make sure the backend server is running on `http://localhost:8000` before using the application.

## Project Detail Page

The project detail page provides a comprehensive view of your project with the following features:

### Navigation
- Access via "View Details" button on project cards
- Direct URL: `/project/{projectId}`

### Tabs
1. **DDL Statements**: 
   - View all DDL statements associated with the project
   - Add new DDL statements via dialog
   - Delete existing DDL statements
   - Syntax highlighting for SQL code

2. **Documentation**:
   - View all project documentation
   - Add new documentation entries
   - Delete existing documentation
   - Support for multi-line text

3. **Question-SQL Pairs**:
   - View all question-SQL example pairs
   - Add new question-SQL pairs
   - Delete existing pairs
   - Separate fields for questions and SQL queries

### Features
- **Real-time Updates**: Changes are immediately reflected in the UI
- **Success Notifications**: Visual feedback for successful operations
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Responsive Design**: Works on desktop and mobile devices

## API Integration

The frontend integrates with the following backend endpoints:

- `GET /projects/{projectId}` - Get project details with all related data
- `POST /projects/{projectId}/ddl-statements` - Add DDL statements
- `POST /projects/{projectId}/documentation-items` - Add documentation
- `POST /projects/{projectId}/question-sql-pairs` - Add question-SQL pairs
- `DELETE /projects/ddl/{itemId}` - Delete DDL statement
- `DELETE /projects/documentation/{itemId}` - Delete documentation
- `DELETE /projects/question-sql/{itemId}` - Delete question-SQL pair

## Development

### Project Structure
```
src/
├── components/
│   ├── ProjectList.jsx      # Project list view
│   ├── ProjectDetail.jsx    # Project detail view with tabs
│   ├── NewProject.jsx       # New project creation
│   ├── ChatList.jsx         # Chat list view
│   ├── ChatDetail.jsx       # Chat interface
│   ├── Layout.jsx           # Main layout component
│   └── ApiErrorBoundary.jsx # Error boundary for API calls
├── services/
│   └── api.js              # API service functions
└── App.jsx                 # Main application component
```

### Key Components

#### ProjectDetail.jsx
The main component for project details with:
- Tabbed interface for different data types
- Add/delete functionality for all item types
- Real-time data updates
- Comprehensive error handling

#### API Service
Centralized API calls with:
- Consistent error handling
- Request/response formatting
- Base URL configuration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.
