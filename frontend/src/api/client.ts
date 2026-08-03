import type { AnalyzeResponse, DemoSummary } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON, keep statusText
    }
    throw new ApiError(detail);
  }
  return res.json() as Promise<T>;
}

export async function analyzePullRequest(prUrl: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pr_url: prUrl }),
  });
  return handleResponse<AnalyzeResponse>(res);
}

export async function fetchDemos(): Promise<DemoSummary[]> {
  const res = await fetch(`${BASE_URL}/api/demos`);
  return handleResponse<DemoSummary[]>(res);
}

export async function fetchDemo(id: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/demos/${id}`);
  return handleResponse<AnalyzeResponse>(res);
}
