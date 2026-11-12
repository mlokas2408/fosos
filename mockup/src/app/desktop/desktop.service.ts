import { Injectable, computed, signal } from '@angular/core';

export type AppId = 'file-explorer';

export interface DesktopApp {
  id: AppId;
  title: string;
  icon: string;
  description: string;
}

export interface OpenWindow {
  id: AppId;
  title: string;
  minimized: boolean;
  zIndex: number;
}

@Injectable({ providedIn: 'root' })
export class DesktopService {
  readonly apps: DesktopApp[] = [
    {
      id: 'file-explorer',
      title: 'File Explorer',
      icon: 'lucideFolder',
      description: 'Browse files and folders',
    },
  ];

  private readonly _startOpen = signal(false);
  private readonly _windows = signal<OpenWindow[]>([]);
  private readonly _focusedId = signal<AppId | null>(null);
  private readonly _selectedDesktopIcon = signal<AppId | null>(null);
  private readonly _zCounter = signal(10);

  readonly startOpen = this._startOpen.asReadonly();
  readonly windows = this._windows.asReadonly();
  readonly focusedId = this._focusedId.asReadonly();
  readonly selectedDesktopIcon = this._selectedDesktopIcon.asReadonly();

  readonly visibleWindows = computed(() => this._windows().filter((w) => !w.minimized));
  readonly taskbarApps = computed(() => this._windows());
  readonly hasOpenWindows = computed(() => this._windows().length > 0);

  toggleStart(): void {
    this._startOpen.update((open) => !open);
  }

  closeStart(): void {
    this._startOpen.set(false);
  }

  selectDesktopIcon(id: AppId | null): void {
    this._selectedDesktopIcon.set(id);
  }

  openApp(id: AppId): void {
    this.closeStart();
    this._selectedDesktopIcon.set(null);
    const existing = this._windows().find((w) => w.id === id);
    if (existing) {
      this.focusWindow(id);
      this._windows.update((list) =>
        list.map((w) => (w.id === id ? { ...w, minimized: false } : w)),
      );
      return;
    }

    const app = this.apps.find((a) => a.id === id);
    const nextZ = this._zCounter() + 1;
    this._zCounter.set(nextZ);
    this._focusedId.set(id);
    this._windows.update((list) => [
      ...list,
      {
        id,
        title: app?.title ?? id,
        minimized: false,
        zIndex: nextZ,
      },
    ]);
  }

  closeWindow(id: AppId): void {
    this._windows.update((list) => list.filter((w) => w.id !== id));
    if (this._focusedId() === id) {
      const remaining = this._windows().filter((w) => !w.minimized);
      const top = [...remaining].sort((a, b) => b.zIndex - a.zIndex)[0];
      this._focusedId.set(top?.id ?? null);
    }
  }

  minimizeWindow(id: AppId): void {
    this._windows.update((list) =>
      list.map((w) => (w.id === id ? { ...w, minimized: true } : w)),
    );
    if (this._focusedId() === id) {
      const remaining = this._windows().filter((w) => w.id !== id && !w.minimized);
      const top = [...remaining].sort((a, b) => b.zIndex - a.zIndex)[0];
      this._focusedId.set(top?.id ?? null);
    }
  }

  toggleMinimize(id: AppId): void {
    const win = this._windows().find((w) => w.id === id);
    if (!win) return;
    if (win.minimized || this._focusedId() !== id) {
      this.focusWindow(id);
      this._windows.update((list) =>
        list.map((w) => (w.id === id ? { ...w, minimized: false } : w)),
      );
    } else {
      this.minimizeWindow(id);
    }
  }

  focusWindow(id: AppId): void {
    const nextZ = this._zCounter() + 1;
    this._zCounter.set(nextZ);
    this._focusedId.set(id);
    this._windows.update((list) =>
      list.map((w) => (w.id === id ? { ...w, zIndex: nextZ } : w)),
    );
  }

  isFocused(id: AppId): boolean {
    return this._focusedId() === id;
  }

  isAppRunning(id: AppId): boolean {
    return this._windows().some((w) => w.id === id);
  }
}
