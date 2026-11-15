import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HlmButtonImports } from '@spartan-ng/helm/button';
import { HlmInputImports } from '@spartan-ng/helm/input';
import { FOS_BRAND } from '../brand/fos-brand';
import { FosMark } from '../brand/fos-mark';

@Component({
  selector: 'app-login',
  imports: [FormsModule, FosMark, HlmButtonImports, HlmInputImports],
  styleUrl: './login.css',
  templateUrl: './login.html',
})
export class Login {
  private readonly router = inject(Router);

  readonly brand = FOS_BRAND;
  readonly username = signal('live');
  readonly password = signal('');
  readonly submitting = signal(false);

  onSubmit(event: Event): void {
    event.preventDefault();
    if (this.submitting()) {
      return;
    }
    this.submitting.set(true);
    void this.router.navigateByUrl('/');
  }
}
