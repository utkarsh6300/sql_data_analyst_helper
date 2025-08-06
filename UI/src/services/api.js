const API_BASE_URL = 'http://localhost:8000';

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

const handleResponse = async (response) => {
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      message: 'An unexpected error occurred'
    }));
    throw new ApiError(error.message || 'An unexpected error occurred', response.status);
  }
  return response.json();
};

export const projectApi = {
  async createProject(projectData) {
    const response = await fetch(`${API_BASE_URL}/projects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(projectData),
    });
    return handleResponse(response);
  },

  async getProjects() {
    const response = await fetch(`${API_BASE_URL}/projects`);
    return handleResponse(response);
  },

  async getProject(projectId) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}`);
    return handleResponse(response);
  },

  async addDocumentationItems(projectId, documentationItems) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/documentation-items`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ documentation_items: documentationItems }),
    });
    return handleResponse(response);
  },

  async addQuestionSqlPairs(projectId, questionSqlPairs) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/question-sql-pairs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question_sql_pairs: questionSqlPairs }),
    });
    return handleResponse(response);
  },

  async addDdlStatements(projectId, ddlStatements) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/ddl-statements`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ddl_statements: ddlStatements }),
    });
    return handleResponse(response);
  },

  async deleteProject(projectId) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  },

  async deleteDocumentationItem(itemId) {
    const response = await fetch(`${API_BASE_URL}/projects/documentation/${itemId}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  },

  async deleteQuestionSqlItem(itemId) {
    const response = await fetch(`${API_BASE_URL}/projects/question-sql/${itemId}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  },

  async deleteDdlItem(itemId) {
    const response = await fetch(`${API_BASE_URL}/projects/ddl/${itemId}`, {
      method: 'DELETE',
    });
    return handleResponse(response);
  },
};

export const chatApi = {
  async getChats(projectId) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/chats`);
    console.log('Response:', response);
    return handleResponse(response);
  },

  async getChat(chatId) {
    const response = await fetch(`${API_BASE_URL}/chats/${chatId}`);
    return handleResponse(response);
  },

  async createChat(projectId) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/chats`, {
      method: 'POST',
    });
    return handleResponse(response);
  },

  async generateSql(chatId, text) {
    const response = await fetch(`${API_BASE_URL}/chats/${chatId}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });
    return handleResponse(response);
  },

  async feedback(chatId, feedback) {
    const response = await fetch(
      `${API_BASE_URL}/chats/${chatId}/feedback`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(feedback)
      }
    );
    return handleResponse(response);
  },

  async updateChat(chatId, update) {
    const response = await fetch(`${API_BASE_URL}/chats/${chatId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(update),
    });
    return handleResponse(response);
  },
};