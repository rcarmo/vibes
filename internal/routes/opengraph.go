package routes

import (
	"context"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"
)

// LinkPreview represents an OpenGraph link preview.
type LinkPreview struct {
	URL         string `json:"url"`
	Title       string `json:"title,omitempty"`
	Description string `json:"description,omitempty"`
	Image       string `json:"image,omitempty"`
	SiteName    string `json:"site_name,omitempty"`
}

// FetchLinkPreview fetches OpenGraph metadata for a URL.
func FetchLinkPreview(url string) (*LinkPreview, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Vibes/1.0 (link preview)")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	// Read first 100KB only
	body, err := io.ReadAll(io.LimitReader(resp.Body, 100*1024))
	if err != nil {
		return nil, err
	}

	html := string(body)
	preview := &LinkPreview{URL: url}

	// Extract OpenGraph meta tags
	preview.Title = extractMeta(html, "og:title")
	if preview.Title == "" {
		preview.Title = extractTitle(html)
	}
	preview.Description = extractMeta(html, "og:description")
	if preview.Description == "" {
		preview.Description = extractMeta(html, "description")
	}
	preview.Image = extractMeta(html, "og:image")
	preview.SiteName = extractMeta(html, "og:site_name")

	return preview, nil
}

var metaRegex = regexp.MustCompile(`<meta[^>]+(?:property|name)=["']([^"']+)["'][^>]+content=["']([^"']+)["']`)
var metaRegexAlt = regexp.MustCompile(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']([^"']+)["']`)
var titleRegex = regexp.MustCompile(`<title[^>]*>([^<]+)</title>`)

func extractMeta(html, property string) string {
	// Try property="X" content="Y" order
	for _, match := range metaRegex.FindAllStringSubmatch(html, -1) {
		if match[1] == property {
			return strings.TrimSpace(match[2])
		}
	}
	// Try content="Y" property="X" order
	for _, match := range metaRegexAlt.FindAllStringSubmatch(html, -1) {
		if match[2] == property {
			return strings.TrimSpace(match[1])
		}
	}
	return ""
}

func extractTitle(html string) string {
	match := titleRegex.FindStringSubmatch(html)
	if len(match) >= 2 {
		return strings.TrimSpace(match[1])
	}
	return ""
}
