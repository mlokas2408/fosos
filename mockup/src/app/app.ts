import { Component, HostListener, inject } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { lucideFolder } from '@ng-icons/lucide';
import { FOS_BRAND } from './brand/fos-brand';
import { FosMark } from './brand/fos-mark';
import { AppId, DesktopService } from './desktop/desktop.service';
import { FileExplorer } from './desktop/file-explorer/file-explorer';
import { Taskbar } from './desktop/taskbar/taskbar';

@Component({
  selector: 'app-root',
  imports: [NgIcon, FosMark, Taskbar, FileExplorer],
  providers: [provideIcons({ lucideFolder })],
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  readonly desktop = inject(DesktopService);
  readonly brand = FOS_BRAND;

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.desktop.closeStart();
    this.desktop.selectDesktopIcon(null);
  }

  @HostListener('document:keydown.enter')
  onEnter(): void {
    const selected = this.desktop.selectedDesktopIcon();
    if (selected) {
      this.desktop.openApp(selected);
    }
  }

  onDesktopClick(): void {
    this.desktop.closeStart();
    this.desktop.selectDesktopIcon(null);
  }

  onIconClick(id: AppId, event: MouseEvent): void {
    event.stopPropagation();
    this.desktop.selectDesktopIcon(id);
  }

  onIconDblClick(id: AppId, event: MouseEvent): void {
    event.stopPropagation();
    this.desktop.openApp(id);
  }
}
