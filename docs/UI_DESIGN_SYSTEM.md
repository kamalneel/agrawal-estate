# UI Design System & Best Practices

This document outlines the design system and best practices for maintaining UI consistency across the Agrawal Estate Planner application.

## Design Philosophy

The application uses a **dark theme by default** with a modern, clean aesthetic inspired by financial platforms. The design emphasizes:
- **Clarity**: Easy to read and understand
- **Consistency**: Uniform patterns across all pages
- **Accessibility**: High contrast and readable typography
- **Performance**: Smooth transitions and interactions

## Design Tokens

### Always Use CSS Variables

**Never use hardcoded colors or values.** Always use the design tokens defined in `frontend/src/styles/tokens.css`.

### Color System

```css
/* Backgrounds */
--color-bg-primary: #0D0D0D      /* Main background */
--color-bg-secondary: #1A1A1A    /* Card backgrounds */
--color-bg-tertiary: #242424     /* Elevated surfaces */
--color-bg-hover: #333333        /* Hover states */

/* Text */
--color-text-primary: #FFFFFF     /* Main text */
--color-text-secondary: #A3A3A3  /* Secondary text */
--color-text-tertiary: #737373    /* Tertiary text */

/* Accent - "Agrawal Green" */
--color-accent: #00D632
--color-accent-hover: #00E639
--color-accent-muted: rgba(0, 214, 50, 0.12)

/* Semantic Colors */
--color-positive: #00D632
--color-negative: #FF5A5A
--color-warning: #FFB800
--color-info: #00A3FF

/* Borders */
--color-border: rgba(255, 255, 255, 0.08)
--color-border-hover: rgba(255, 255, 255, 0.15)
```

### Spacing System

```css
--space-1: 0.25rem   /* 4px */
--space-2: 0.5rem    /* 8px */
--space-3: 0.75rem   /* 12px */
--space-4: 1rem      /* 16px */
--space-5: 1.25rem   /* 20px */
--space-6: 1.5rem    /* 24px */
--space-8: 2rem      /* 32px */
```

### Typography

```css
/* Font Families */
--font-sans: 'Outfit', -apple-system, sans-serif
--font-display: 'Space Grotesk', sans-serif
--font-mono: 'JetBrains Mono', monospace

/* Font Sizes */
--text-xs: 0.75rem
--text-sm: 0.875rem
--text-base: 1rem
--text-lg: 1.125rem
--text-xl: 1.25rem
--text-2xl: 1.5rem
--text-3xl: 1.875rem
--text-4xl: 2.25rem

/* Font Weights */
--font-normal: 400
--font-medium: 500
--font-semibold: 600
--font-bold: 700
```

### Border Radius

```css
--radius-sm: 0.375rem   /* 6px */
--radius-md: 0.5rem     /* 8px */
--radius-lg: 0.75rem     /* 12px */
--radius-xl: 1rem       /* 16px */
```

### Transitions

```css
--duration-fast: 150ms
--duration-normal: 200ms
--duration-slow: 300ms
```

## Component Patterns

### Page Container

```css
.container {
  padding: var(--space-6);
  max-width: 1400px;
  margin: 0 auto;
}
```

### Page Header

**Structure:**
```tsx
<div className={styles.header}>
  <div className={styles.headerContent}>
    <div className={styles.headerIcon}>
      <IconComponent size={24} />
    </div>
    <div>
      <h1 className={styles.title}>Page Title</h1>
      <p className={styles.subtitle}>Page description</p>
    </div>
  </div>
  {/* Optional action buttons */}
</div>
```

**Styles:**
```css
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-6);
}

.headerContent {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.headerIcon {
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, #10B981 0%, #059669 100%);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.title {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  margin: 0;
}

.subtitle {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin: var(--space-1) 0 0 0;
}
```

### Cards

```css
.card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: all var(--duration-fast);
}

.card:hover {
  border-color: var(--color-border-hover);
  background: var(--color-bg-tertiary);
}
```

### Buttons

**Primary Button:**
```css
.primaryButton {
  padding: var(--space-2) var(--space-4);
  background: var(--color-accent);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-fast);
}

.primaryButton:hover {
  background: var(--color-accent-hover);
}
```

**Secondary Button:**
```css
.secondaryButton {
  padding: var(--space-2) var(--space-4);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-fast);
}

.secondaryButton:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  border-color: var(--color-border-hover);
}
```

### Form Inputs

```css
.input {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  transition: border-color var(--duration-fast);
}

.input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.label {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-text-primary);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
}
```

### Badges

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.badge.positive {
  background: var(--color-positive-muted);
  color: var(--color-positive);
}

.badge.negative {
  background: var(--color-negative-muted);
  color: var(--color-negative);
}
```

## Common Patterns

### Summary Cards

```css
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.summaryCard {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  text-align: center;
}

.summaryValue {
  font-size: var(--text-4xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
  font-family: var(--font-mono);
}

.summaryLabel {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}
```

### Status Indicators

```css
.statusBadge {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.statusBadge.enabled {
  background: var(--color-positive-muted);
  color: var(--color-positive);
}

.statusBadge.disabled {
  background: var(--color-bg-tertiary);
  color: var(--color-text-tertiary);
}
```

## Best Practices

### ✅ DO

1. **Always use CSS variables** from the design tokens
2. **Use semantic spacing** (`var(--space-X)`) instead of pixel values
3. **Follow the component patterns** shown above
4. **Use consistent border radius** (`var(--radius-md)` for most elements)
5. **Apply transitions** to interactive elements (`transition: all var(--duration-fast)`)
6. **Use the correct font families**:
   - `var(--font-display)` for headings
   - `var(--font-sans)` for body text
   - `var(--font-mono)` for numbers/values
7. **Maintain consistent hover states** (border color and background changes)
8. **Use semantic colors** for status indicators (positive, negative, warning, info)

### ❌ DON'T

1. **Never use hardcoded colors** like `#ffffff`, `#000000`, `#1f2937`, etc.
2. **Don't use pixel values** for spacing (use `var(--space-X)`)
3. **Don't create custom color schemes** - use the design tokens
4. **Don't mix light and dark theme styles** - stick to the dark theme tokens
5. **Don't use inline styles** for colors or spacing
6. **Don't create new component patterns** without checking existing patterns first
7. **Don't use opacity for disabled states** - use appropriate background/text colors

## Migration Checklist

When updating an existing page to match the design system:

- [ ] Replace all hardcoded colors with CSS variables
- [ ] Replace pixel spacing with `var(--space-X)`
- [ ] Update border radius to use `var(--radius-X)`
- [ ] Use design token font sizes and weights
- [ ] Update button styles to match patterns
- [ ] Update card styles to use `var(--color-bg-secondary)` and borders
- [ ] Add proper hover states with transitions
- [ ] Use semantic colors for status indicators
- [ ] Test in both light and dark themes (if applicable)
- [ ] Verify accessibility (contrast ratios)

## Examples

### Before (Inconsistent)
```css
.card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1.5rem;
  color: #1f2937;
}
```

### After (Consistent)
```css
.card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  color: var(--color-text-primary);
}
```

## Resources

- **Design Tokens**: `frontend/src/styles/tokens.css`
- **Global Styles**: `frontend/src/styles/globals.css`
- **Reference Implementation**: `frontend/src/pages/OptionsSelling.module.css`

## Questions?

If you're unsure about which token to use or how to implement a pattern, check:
1. Existing pages (OptionsSelling, TaxPlanning, etc.)
2. The design tokens file
3. This document

Maintaining consistency is crucial for a professional, cohesive user experience.



