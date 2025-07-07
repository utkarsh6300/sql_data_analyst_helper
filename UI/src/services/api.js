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

  async addDocumentation(projectId, documentationData) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/documentation`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(documentationData),
    });
    return handleResponse(response);
  },

  async addSchema(projectId, schemaData) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/schema`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(schemaData),
    });
    return handleResponse(response);
  },

  async addSampleQueries(projectId, sampleQueriesData) {
    const response = await fetch(`${API_BASE_URL}/projects/${projectId}/sample-queries`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(sampleQueriesData),
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

  async generateSql(projectId, chatId, text) {
    const response = await fetch(`${API_BASE_URL}/chats/${chatId}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });
    return handleResponse(response);
  },

  async feedback(projectId, chatId, feedback) {
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
};