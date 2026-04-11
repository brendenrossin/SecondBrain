# SecondBrain Demo Deck

Self-contained reveal.js presentation. Open `index.html` in any browser.

## Recording GIFs

### Setup
1. Install OBS Studio
2. Set capture region to 1280x720
3. Record as .mkv (or .mp4)

### Per-slide instructions
Press **S** during the presentation to open speaker notes view. Each feature slide has detailed capture instructions.

### Converting recordings to GIFs

```bash
# Basic conversion (good quality, reasonable size)
ffmpeg -i recording.mkv -vf "fps=12,scale=800:-1:flags=lanczos" -loop 0 output.gif

# Higher quality with palette optimization (recommended)
ffmpeg -i recording.mkv -vf "fps=12,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" output.gif

# If the GIF is too large (>5MB), reduce fps or scale
ffmpeg -i recording.mkv -vf "fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" output.gif
```

### Embedding GIFs
Place converted GIFs in `demo/gifs/` and uncomment the `<img>` tags in `index.html`.

Each slide has a comment showing the exact replacement:
```html
<!-- Replace with: <img src="gifs/home-briefing.gif" alt="Morning Briefing"> -->
```

## Keyboard shortcuts
- **Arrow keys** or **Space**: Navigate slides
- **S**: Speaker notes (capture instructions)
- **F**: Fullscreen
- **Esc**: Slide overview
