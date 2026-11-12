import { Component, inject, output } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideFolder,
  lucideLogOut,
  lucidePower,
  lucideSearch,
  lucideSettings,
  lucideTerminal,
  lucideUser,
} from '@ng-icons/lucide';
import { HlmBadgeImports } from '@spartan-ng/helm/badge';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmCardImports } from '@spartan-ng/helm/card';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { HlmKbdImports } from '@spartan-ng/helm/kbd';
import { FOS_BRAND } from '../../brand/fos-brand';
import { FosMark } from '../../brand/fos-mark';
import { DesktopService } from '../desktop.service';

@Component({
  selector: 'app-start-menu',
  imports: [
    NgIcon,
    FosMark,
    HlmBadgeImports,
    HlmButtonImports,
    HlmCardImports,
    HlmInputImports,
    HlmKbdImports,
  ],
  providers: [
    provideIcons({
      lucideFolder,
      lucideLogOut,
      lucidePower,
      lucideSearch,
      lucideSettings,
      lucideTerminal,
      lucideUser,
    }),
  ],
  host: {
    class: 'pointer-events-auto absolute bottom-full left-0 z-50 mb-px w-[420px]',
  },
  template: `
    <section hlmCard class="w-full shadow-2xl" role="menu" aria-label="FosOS Start menu">
      <div hlmCardHeader class="border-b pb-3">
        <div class="flex items-center gap-2.5">
          <app-fos-mark size="md" [inverse]="true" />
          <div class="min-w-0">
            <h3 hlmCardTitle class="flex items-baseline gap-0">
              <span>Fos</span><span class="font-normal opacity-80">OS</span>
            </h3>
            <p hlmCardDescription>{{ brand.etymology }}</p>
          </div>
        </div>
        <div hlmCardAction class="flex items-center gap-1.5">
          <span hlmBadge variant="secondary">{{ brand.tagline }}</span>
          <kbd hlmKbd>Esc</kbd>
        </div>
      </div>

      <div hlmCardContent class="space-y-5">
        <div class="relative">
          <ng-icon
            name="lucideSearch"
            class="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2"
          />
          <input hlmInput class="ps-8" placeholder="Search FosOS" autofocus />
        </div>

        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <p class="text-muted-foreground text-xs font-medium">Pinned</p>
            <p class="text-muted-foreground text-[11px]">1 app</p>
          </div>
          <div class="grid grid-cols-3 gap-2">
            @for (app of desktop.apps; track app.id) {
              <button
                hlmBtn
                variant="outline"
                type="button"
                class="h-auto flex-col gap-2 px-2 py-3"
                (click)="launch(app.id)"
              >
                <span
                  class="bg-primary text-primary-foreground flex size-9 items-center justify-center"
                >
                  <ng-icon [name]="app.icon" />
                </span>
                <span class="w-full truncate text-[11px] font-medium">{{ app.title }}</span>
              </button>
            }
            <button
              hlmBtn
              variant="ghost"
              type="button"
              class="text-muted-foreground h-auto flex-col gap-2 px-2 py-3"
              disabled
            >
              <span class="bg-muted flex size-9 items-center justify-center">
                <ng-icon name="lucideTerminal" />
              </span>
              <span class="w-full truncate text-[11px] font-medium">Terminal</span>
            </button>
          </div>
        </div>

        <div class="space-y-2">
          <p class="text-muted-foreground text-xs font-medium">Recommended</p>
          <div class="space-y-1">
            <button
              hlmBtn
              variant="ghost"
              class="h-auto w-full justify-start gap-3 px-2 py-2"
              type="button"
              (click)="launch('file-explorer')"
            >
              <span class="bg-muted flex size-8 items-center justify-center">
                <ng-icon name="lucideFolder" />
              </span>
              <span class="min-w-0 flex-1 text-left">
                <span class="block truncate text-xs font-medium">Documents</span>
                <span class="text-muted-foreground block truncate text-[11px]"
                  >Projects · Reports · Archive</span
                >
              </span>
              <span class="text-muted-foreground text-[11px]">Today</span>
            </button>
            <button
              hlmBtn
              variant="ghost"
              class="h-auto w-full justify-start gap-3 px-2 py-2"
              type="button"
              (click)="launch('file-explorer')"
            >
              <span class="bg-muted flex size-8 items-center justify-center">
                <ng-icon name="lucideFolder" />
              </span>
              <span class="min-w-0 flex-1 text-left">
                <span class="block truncate text-xs font-medium">Downloads</span>
                <span class="text-muted-foreground block truncate text-[11px]"
                  >Recently used folder</span
                >
              </span>
              <span class="text-muted-foreground text-[11px]">Yesterday</span>
            </button>
          </div>
        </div>
      </div>

      <div hlmCardFooter class="justify-between">
        <button hlmBtn variant="ghost" size="sm" type="button" class="gap-2">
          <span class="bg-secondary flex size-6 items-center justify-center">
            <ng-icon name="lucideUser" class="text-xs" />
          </span>
          User
        </button>
        <div class="flex items-center gap-1">
          <button hlmBtn variant="outline" size="icon-sm" type="button" aria-label="Settings">
            <ng-icon name="lucideSettings" />
          </button>
          <button hlmBtn variant="outline" size="icon-sm" type="button" aria-label="Sign out">
            <ng-icon name="lucideLogOut" />
          </button>
          <button hlmBtn variant="outline" size="icon-sm" type="button" aria-label="Power">
            <ng-icon name="lucidePower" />
          </button>
        </div>
      </div>
    </section>
  `,
})
export class StartMenu {
  readonly desktop = inject(DesktopService);
  readonly brand = FOS_BRAND;
  readonly closed = output<void>();

  launch(id: 'file-explorer'): void {
    this.desktop.openApp(id);
    this.closed.emit();
  }
}
