# Publish the interactive typhoon map on your GitHub Pages website

**The map file is completely self-contained.** No hosted database, JavaScript dependencies, or special internet services are needed. It includes 529 storms and municipality boundaries.

## If your repository is the Hugo Blox SOURCE project

Copy the three items under `HUGO_BLOX_SOURCE/` into the same relative locations in the GitHub repository:

- `static/maps/typhoons/index.html` — creates the standalone map page.
- `layouts/shortcodes/typhoon-map.html` — permits embedding the map on a Hugo page.
- `content/research/typhoon-wind-exposure.md` — creates a research landing page with the map embedded.

Commit/push changes to the actual source branch your deployment workflow builds. Do NOT manually edit `public/`, which Hugo may regenerate.

After deployment the map will appear at `<your published site root>/maps/typhoons/`. The research page should appear at `<your published site root>/research/typhoon-wind-exposure/` unless your Hugo project customizes permalinks.

To link the map in your menu, add a link to `maps/typhoons/` (or the research page) via your site's existing menu configuration. Use a site-relative URL consistent with your configured baseURL.

## If the repository is already the PUBLISHED HTML site

Copy `PLAIN_GITHUB_PAGES_SOURCE/maps/typhoons/index.html` into a `maps/typhoons/` directory at the root of your **published** branch/folder.

To embed in an existing HTML page:

```html
<iframe src="maps/typhoons/" title="Interactive Philippine typhoon wind exposure" style="width:100%;height:800px;border:0;"></iframe>
```

If the containing page is in a subdirectory, adjust the relative `src` to the actual map route, or use the absolute published URL.

## Publishing and URL caveat

The GitHub owner appears as `holly-jansen`, while the repository name provided is `hollyejansen.github.io`. A repo whose name does not exactly match `<owner>.github.io` is normally published as a PROJECT site, e.g. `https://holly-jansen.github.io/hollyejansen.github.io/`, unless you have a custom domain. Confirm your actual site address in Repository -> Settings -> Pages rather than assuming `hollyejansen.github.io`.

## Important

The lighter embedded map offers the primary continuous population-weighted squared-wind exposure measure. Its data are static: if you revise the exposure master, you must regenerate and replace `index.html`. The map does NOT host the 42 MB CSV; its visualized data are embedded.
