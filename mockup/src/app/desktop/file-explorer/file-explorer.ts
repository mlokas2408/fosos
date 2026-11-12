import { Component, input, output, signal } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideArrowLeft,
  lucideArrowRight,
  lucideArrowUp,
  lucideChevronRight,
  lucideDownload,
  lucideFile,
  lucideFileSpreadsheet,
  lucideFileText,
  lucideFolder,
  lucideHardDrive,
  lucideHome,
  lucideImage,
  lucideLayoutGrid,
  lucideList,
  lucideMinus,
  lucideMonitor,
  lucideMusic,
  lucideRefreshCw,
  lucideSearch,
  lucideSquare,
  lucideX,
} from '@ng-icons/lucide';
import { NgScrollbar } from 'ngx-scrollbar';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmCardImports } from '@spartan-ng/helm/card';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmScrollAreaImports } from '@spartan-ng/helm/scroll-area';
import { HlmSeparatorImports } from '@spartan-ng/helm/separator';

interface ExplorerItem {
  name: string;
  type: 'folder' | 'file';
  icon: string;
  modified: string;
  size: string;
}

@Component({
  selector: 'app-file-explorer',
  imports: [
    NgIcon,
    NgScrollbar,
    HlmBadgeImports,
    HlmButtonImports,
    HlmCardImports,
    HlmInputImports,
    HlmScrollAreaImports,
    HlmSeparatorImports,
  ],
  providers: [
    provideIcons({
      lucideArrowLeft,
      lucideArrowRight,
      lucideArrowUp,
      lucideChevronRight,
      lucideDownload,
      lucideFile,
      lucideFileSpreadsheet,
      lucideFileText,
      lucideFolder,
      lucideHardDrive,
      lucideHome,
      lucideImage,
      lucideLayoutGrid,
      lucideList,
      lucideMinus,
      lucideMonitor,
      lucideMusic,
      lucideRefreshCw,
      lucideSearch,
      lucideSquare,
      lucideX,
    }),
  ],
  host: {
    class: 'block h-full w-full',
  },
  template: `
    <section
      hlmCard
      class="flex h-full w-full flex-col overflow-hidden py-0 shadow-2xl transition-[box-shadow,opacity]"
      [class.ring-foreground/20]="focused()"
      [class.opacity-90]="!focused()"
      (pointerdown)="focus.emit()"
    >
      <header
        class="flex h-10 shrink-0 items-center gap-2 border-b border-border px-2"
        [class.bg-muted/40]="focused()"
        [class.bg-muted/20]="!focused()"
      >
        <span class="bg-primary text-primary-foreground flex size-6 items-center justify-center">
          <ng-icon name="lucideFolder" class="text-sm" />
        </span>
        <h3 hlmCardTitle class="flex-1 truncate">{{ title() }}</h3>
        <span hlmBadge variant="secondary">Documents</span>
        <button
          hlmBtn
          variant="ghost"
          size="icon-xs"
          type="button"
          aria-label="Minimize"
          (click)="minimize.emit(); $event.stopPropagation()"
        >
          <ng-icon name="lucideMinus" />
        </button>
        <button hlmBtn variant="ghost" size="icon-xs" type="button" aria-label="Maximize" disabled>
          <ng-icon name="lucideSquare" />
        </button>
        <button
          hlmBtn
          variant="ghost"
          size="icon-xs"
          type="button"
          class="hover:bg-destructive/15 hover:text-destructive"
          aria-label="Close"
          (click)="close.emit(); $event.stopPropagation()"
        >
          <ng-icon name="lucideX" />
        </button>
      </header>

      <div class="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1.5">
        <button hlmBtn variant="ghost" size="icon-xs" type="button" aria-label="Back" disabled>
          <ng-icon name="lucideArrowLeft" />
        </button>
        <button hlmBtn variant="ghost" size="icon-xs" type="button" aria-label="Forward" disabled>
          <ng-icon name="lucideArrowRight" />
        </button>
        <button hlmBtn variant="ghost" size="icon-xs" type="button" aria-label="Up">
          <ng-icon name="lucideArrowUp" />
        </button>
        <button hlmBtn variant="ghost" size="icon-xs" type="button" aria-label="Refresh">
          <ng-icon name="lucideRefreshCw" />
        </button>

        <hlm-separator orientation="vertical" class="mx-1 h-6" />

        <div
          class="border-input bg-input/30 flex min-w-0 flex-1 items-center gap-1.5 border px-2 py-1 text-xs"
        >
          <ng-icon name="lucideHome" class="text-muted-foreground shrink-0 text-sm" />
          <ng-icon name="lucideChevronRight" class="text-muted-foreground shrink-0 text-xs" />
          <span class="text-muted-foreground">FosOS</span>
          <ng-icon name="lucideChevronRight" class="text-muted-foreground shrink-0 text-xs" />
          <span class="truncate font-medium">Documents</span>
        </div>

        <div class="relative w-44 shrink-0">
          <ng-icon
            name="lucideSearch"
            class="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
          />
          <input hlmInput class="h-7 ps-8" placeholder="Search" />
        </div>

        <hlm-separator orientation="vertical" class="mx-1 h-6" />

        <button
          hlmBtn
          [variant]="viewMode() === 'grid' ? 'secondary' : 'ghost'"
          size="icon-xs"
          type="button"
          aria-label="Grid view"
          (click)="viewMode.set('grid')"
        >
          <ng-icon name="lucideLayoutGrid" />
        </button>
        <button
          hlmBtn
          [variant]="viewMode() === 'list' ? 'secondary' : 'ghost'"
          size="icon-xs"
          type="button"
          aria-label="List view"
          (click)="viewMode.set('list')"
        >
          <ng-icon name="lucideList" />
        </button>
      </div>

      <div class="flex min-h-0 flex-1">
        <aside class="bg-muted/20 flex w-44 shrink-0 flex-col gap-0.5 border-r border-border p-2">
          <p class="text-muted-foreground px-2 pb-1 text-[10px] font-medium tracking-wide uppercase">
            Quick access
          </p>
          @for (nav of quickAccess; track nav.label) {
            <button
              hlmBtn
              [variant]="nav.active ? 'secondary' : 'ghost'"
              size="sm"
              type="button"
              class="w-full justify-start gap-2"
            >
              <ng-icon [name]="nav.icon" />
              {{ nav.label }}
            </button>
          }
        </aside>

        <ng-scrollbar hlm class="min-h-0 flex-1">
          <div hlmCardContent class="space-y-4 pt-4 pb-4">
            @if (viewMode() === 'grid') {
              <div class="space-y-2">
                <p class="text-muted-foreground text-xs font-medium">Folders</p>
                <div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  @for (item of folders; track item.name) {
                    <button
                      hlmBtn
                      [variant]="selected() === item.name ? 'secondary' : 'outline'"
                      type="button"
                      class="h-auto flex-col gap-2 px-3 py-3"
                      (click)="selected.set(item.name)"
                    >
                      <ng-icon [name]="item.icon" class="text-2xl" />
                      <span class="w-full truncate text-xs font-medium">{{ item.name }}</span>
                    </button>
                  }
                </div>
              </div>

              <hlm-separator />

              <div class="space-y-2">
                <p class="text-muted-foreground text-xs font-medium">Files</p>
                <div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  @for (file of files; track file.name) {
                    <button
                      hlmBtn
                      [variant]="selected() === file.name ? 'secondary' : 'outline'"
                      type="button"
                      class="h-auto flex-col gap-2 px-3 py-3"
                      (click)="selected.set(file.name)"
                    >
                      <ng-icon [name]="file.icon" class="text-2xl" />
                      <span class="w-full truncate text-xs font-medium">{{ file.name }}</span>
                    </button>
                  }
                </div>
              </div>
            } @else {
              <div class="overflow-hidden border border-border">
                <div
                  class="bg-muted/50 text-muted-foreground grid grid-cols-[1fr_7rem_5rem] gap-2 px-3 py-1.5 text-[11px] font-medium"
                >
                  <span>Name</span>
                  <span>Modified</span>
                  <span class="text-right">Size</span>
                </div>
                @for (item of allItems; track item.name) {
                  <button
                    type="button"
                    class="hover:bg-accent grid w-full grid-cols-[1fr_7rem_5rem] gap-2 border-t border-border px-3 py-2 text-left text-xs transition-colors"
                    [class.bg-accent]="selected() === item.name"
                    (click)="selected.set(item.name)"
                  >
                    <span class="flex min-w-0 items-center gap-2">
                      <ng-icon [name]="item.icon" class="text-muted-foreground shrink-0 text-sm" />
                      <span class="truncate">{{ item.name }}</span>
                    </span>
                    <span class="text-muted-foreground">{{ item.modified }}</span>
                    <span class="text-muted-foreground text-right">{{ item.size || '—' }}</span>
                  </button>
                }
              </div>
            }
          </div>
        </ng-scrollbar>
      </div>

      <footer
        class="text-muted-foreground flex h-8 shrink-0 items-center justify-between gap-3 border-t border-border px-3 text-[11px]"
      >
        <span
          >{{ allItems.length }} items
          @if (selected()) {
            <span class="text-foreground">· {{ selected() }}</span>
          }
        </span>
        <span>FosOS \\ Documents</span>
      </footer>
    </section>
  `,
})
export class FileExplorer {
  readonly title = input('File Explorer');
  readonly focused = input(true);
  readonly close = output<void>();
  readonly minimize = output<void>();
  readonly focus = output<void>();

  readonly viewMode = signal<'grid' | 'list'>('list');
  readonly selected = signal<string | null>(null);

  readonly quickAccess = [
    { label: 'Home', icon: 'lucideHome', active: false },
    { label: 'Desktop', icon: 'lucideMonitor', active: false },
    { label: 'Documents', icon: 'lucideFolder', active: true },
    { label: 'Downloads', icon: 'lucideDownload', active: false },
    { label: 'Pictures', icon: 'lucideImage', active: false },
    { label: 'Music', icon: 'lucideMusic', active: false },
    { label: 'FosOS', icon: 'lucideHardDrive', active: false },
  ];

  readonly folders: ExplorerItem[] = [
    { name: 'Projects', type: 'folder', icon: 'lucideFolder', modified: 'Today', size: '' },
    { name: 'Reports', type: 'folder', icon: 'lucideFolder', modified: 'Yesterday', size: '' },
    { name: 'Archive', type: 'folder', icon: 'lucideFolder', modified: 'Oct 28', size: '' },
  ];

  readonly files: ExplorerItem[] = [
    {
      name: 'Budget 2026.xlsx',
      type: 'file',
      icon: 'lucideFileSpreadsheet',
      modified: 'Today',
      size: '128 KB',
    },
    {
      name: 'Meeting notes.md',
      type: 'file',
      icon: 'lucideFileText',
      modified: 'Yesterday',
      size: '4 KB',
    },
    {
      name: 'Presentation.pptx',
      type: 'file',
      icon: 'lucideFile',
      modified: 'Nov 8',
      size: '2.1 MB',
    },
    {
      name: 'Readme.txt',
      type: 'file',
      icon: 'lucideFileText',
      modified: 'Nov 1',
      size: '1 KB',
    },
  ];

  readonly allItems = [...this.folders, ...this.files];
}
