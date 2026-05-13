import type { ApiErrorPayload } from "../types/api";

export class ApiRequestError extends Error {
  status: number;
  payload: ApiErrorPayload;

  constructor(message: string, status: number, payload: ApiErrorPayload) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}
