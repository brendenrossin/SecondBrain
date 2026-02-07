"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
          <AlertTriangle className="w-8 h-8 text-danger mb-3" />
          <h3 className="text-sm font-medium mb-1">Something went wrong</h3>
          <p className="text-xs text-text-muted mb-3 max-w-[300px]">
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="text-xs text-accent hover:text-accent-hover"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
