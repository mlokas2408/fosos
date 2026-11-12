import { Component, input } from '@angular/core';

export type FosMarkSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

@Component({
  selector: 'app-fos-mark',
  host: {
    class: 'inline-flex shrink-0',
    '[attr.aria-hidden]': 'decorative() ? "true" : null',
    '[attr.aria-label]': 'decorative() ? null : "FosOS"',
    role: 'img',
  },
  template: `
    <span
      class="fos-mark relative inline-flex items-center justify-center border font-medium select-none"
      [class]="sizeClass()"
      [class.bg-primary]="inverse()"
      [class.text-primary-foreground]="inverse()"
      [class.border-primary]="inverse()"
      [class.bg-transparent]="!inverse()"
      [class.text-foreground]="!inverse()"
      [class.border-foreground]="!inverse()"
    >
      <span class="leading-none tracking-tight">F</span>
    </span>
  `,
  styles: `
    :host {
      display: inline-flex;
    }
    .fos-mark {
      border-radius: 0;
    }
  `,
})
export class FosMark {
  readonly size = input<FosMarkSize>('md');
  /** White fill / dark F — for primary buttons and start open state */
  readonly inverse = input(false);
  readonly decorative = input(true);

  sizeClass(): string {
    switch (this.size()) {
      case 'xs':
        return 'size-4 text-[9px]';
      case 'sm':
        return 'size-5 text-[10px]';
      case 'md':
        return 'size-6 text-xs';
      case 'lg':
        return 'size-8 text-sm';
      case 'xl':
        return 'size-12 text-xl';
    }
  }
}
