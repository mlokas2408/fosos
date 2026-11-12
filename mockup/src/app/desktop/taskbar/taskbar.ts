import { DatePipe } from '@angular/common';
import { Component, effect, inject, signal } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideBell, lucideFolder, lucideVolume2, lucideWifi } from '@ng-icons/lucide';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmSeparatorImports } from '@spartan-ng/helm/separator';
import { HlmTooltipImports } from '@spartan-ng/helm/tooltip';
import { FOS_BRAND } from '../../brand/fos-brand';
import { FosMark } from '../../brand/fos-mark';
import { DesktopService } from '../desktop.service';
import { StartMenu } from '../start-menu/start-menu';

@Component({
  selector: 'app-taskbar',
  imports: [
    DatePipe,
    NgIcon,
    FosMark,
    HlmBadgeImports,
    HlmButtonImports,
    HlmSeparatorImports,
    HlmTooltipImports,
    StartMenu,
  ],
  providers: [provideIcons({ lucideBell, lucideFolder, lucideVolume2, lucideWifi })],
  host: {
    class: 'pointer-events-none absolute inset-x-0 bottom-0 z-[100]',
  },
  template: `
    <div class="pointer-events-auto relative">
      @if (desktop.startOpen()) {
        <app-start-menu class="start-enter" (closed)="desktop.closeStart()" />
      }

      <div
        class="border-border bg-card/95 text-card-foreground flex h-12 w-full items-center gap-1 border-t px-2 backdrop-blur-md"
      >
        <button
          hlmBtn
          [variant]="desktop.startOpen() ? 'default' : 'ghost'"
          size="icon"
          type="button"
          aria-label="FosOS Start"
          [attr.aria-expanded]="desktop.startOpen()"
          [hlmTooltip]="brand.name"
          position="top"
          (click)="desktop.toggleStart(); $event.stopPropagation()"
        >
          <app-fos-mark size="sm" [inverse]="desktop.startOpen()" [decorative]="true" />
        </button>

        <hlm-separator orientation="vertical" class="mx-1 h-7" />

        <div class="flex items-center gap-0.5">
          @for (app of desktop.apps; track app.id) {
            <div class="relative flex flex-col items-center">
              <button
                hlmBtn
                [variant]="isAppActive(app.id) ? 'secondary' : 'ghost'"
                size="icon"
                type="button"
                [attr.aria-label]="app.title"
                [hlmTooltip]="app.title"
                position="top"
                (click)="onAppClick(app.id); $event.stopPropagation()"
              >
                <ng-icon [name]="app.icon" />
              </button>
              <span
                class="taskbar-indicator absolute -bottom-0.5 h-0.5 bg-primary"
                [class.w-4]="desktop.isAppRunning(app.id)"
                [class.w-0]="!desktop.isAppRunning(app.id)"
                [class.bg-foreground]="desktop.isFocused(app.id) && isAppActive(app.id)"
                aria-hidden="true"
              ></span>
            </div>
          }
        </div>

        <div class="flex-1"></div>

        <span hlmBadge variant="outline" class="me-1 hidden sm:inline-flex">{{ brand.liveLabel }}</span>

        <div class="flex items-center gap-0.5">
          <button
            hlmBtn
            variant="ghost"
            size="icon-sm"
            type="button"
            aria-label="Volume"
            hlmTooltip="Volume"
            position="top"
          >
            <ng-icon name="lucideVolume2" />
          </button>
          <button
            hlmBtn
            variant="ghost"
            size="icon-sm"
            type="button"
            aria-label="Network"
            hlmTooltip="Connected"
            position="top"
          >
            <ng-icon name="lucideWifi" />
          </button>
          <button
            hlmBtn
            variant="ghost"
            size="icon-sm"
            type="button"
            aria-label="Notifications"
            hlmTooltip="Notifications"
            position="top"
          >
            <ng-icon name="lucideBell" />
          </button>

          <hlm-separator orientation="vertical" class="mx-1 h-7" />

          <button
            hlmBtn
            variant="ghost"
            type="button"
            class="h-9 gap-2 px-2.5"
            aria-label="Clock"
            hlmTooltip="Date & time"
            position="top"
          >
            <div class="text-right text-[11px] leading-tight">
              <div class="text-foreground font-medium tabular-nums">
                {{ now() | date: 'HH:mm' }}
              </div>
              <div class="text-muted-foreground tabular-nums">
                {{ now() | date: 'EEE, MMM d' }}
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  `,
})
export class Taskbar {
  readonly desktop = inject(DesktopService);
  readonly brand = FOS_BRAND;
  readonly now = signal(new Date());

  constructor() {
    effect((onCleanup) => {
      const id = setInterval(() => this.now.set(new Date()), 15_000);
      onCleanup(() => clearInterval(id));
    });
  }

  isAppActive(id: string): boolean {
    return this.desktop.taskbarApps().some((w) => w.id === id && !w.minimized);
  }

  onAppClick(id: 'file-explorer'): void {
    if (this.desktop.isAppRunning(id)) {
      this.desktop.toggleMinimize(id);
    } else {
      this.desktop.openApp(id);
    }
  }
}
