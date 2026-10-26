/** The single selected part id, shared by the tree, the viewport and the properties panel. */
export class Selection {
  private current: string | null = null;
  private readonly listeners = new Set<(id: string | null) => void>();

  get(): string | null {
    return this.current;
  }

  set(id: string | null): void {
    if (id === this.current) return;
    this.current = id;
    for (const listener of [...this.listeners]) listener(id);
  }

  onChange(listener: (id: string | null) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
}
