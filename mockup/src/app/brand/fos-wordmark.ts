import { Component, input } from '@angular/core';
import { FOS_BRAND } from './fos-brand';
import { FosMark, type FosMarkSize } from './fos-mark';

@Component({
  selector: 'app-fos-wordmark',
  imports: [FosMark],
  template: `
    <span class="inline-flex items-center gap-2" [class.flex-col]="stacked()" [class.items-start]="stacked()">
      @if (showMark()) {
        <app-fos-mark [size]="markSize()" [inverse]="inverseMark()" />
      }
      <span [class]="stacked() ? 'flex flex-col gap-0.5' : 'inline-flex items-baseline gap-0'">
        <span class="text-foreground font-medium tracking-tight">
          <span>Fos</span><span class="font-normal opacity-80">OS</span>
        </span>
        @if (showTagline()) {
          <span class="text-muted-foreground text-[11px] font-normal tracking-wide">
            {{ brand.tagline }}
          </span>
        }
      </span>
    </span>
  `,
})
export class FosWordmark {
  readonly brand = FOS_BRAND;
  readonly showMark = input(true);
  readonly showTagline = input(false);
  readonly stacked = input(false);
  readonly markSize = input<FosMarkSize>('md');
  readonly inverseMark = input(false);
}
