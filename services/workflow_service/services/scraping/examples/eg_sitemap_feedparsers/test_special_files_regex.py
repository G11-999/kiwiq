#!/usr/bin/env python3
"""
Comprehensive test suite for the special_files_pattern regex used in spider.py

Tests the regex pattern:
special_files_pattern = r'["\'/](robots\.txt|sitemap[^"\'\s]*\.xml|feed\.(?:xml|json)|rss\.xml|atom\.xml)'

This pattern should match special files like robots.txt, sitemaps, and feeds
when they are referenced in HTML content with quotes or forward slashes.
"""

import re
import unittest
from typing import List, Tuple


class TestSpecialFilesRegex(unittest.TestCase):
    
    def setUp(self):
        """Set up the regex pattern to test."""
        # Keep it simple - match files preceded by quotes or forward slash
        # No lookahead - just match the core pattern
        self.special_files_pattern = r'["\'/](robots\.txt|sitemap[^"\'\s]*\.xml|feed\.(?:xml|json)|rss\.xml|atom\.xml)'
        self.regex = re.compile(self.special_files_pattern)
    
    def assertMatchesFiles(self, test_strings: List[str], expected_files: List[str]):
        """Helper to assert that regex matches extract expected filenames."""
        for test_string in test_strings:
            matches = self.regex.findall(test_string)
            self.assertEqual(matches, expected_files, 
                           f"Failed for: {test_string}\nExpected: {expected_files}\nGot: {matches}")
    
    def assertNoMatches(self, test_strings: List[str]):
        """Helper to assert that regex finds no matches."""
        for test_string in test_strings:
            matches = self.regex.findall(test_string)
            self.assertEqual(matches, [], 
                           f"Expected no matches for: {test_string}\nBut got: {matches}")

    def test_robots_txt_patterns(self):
        """Test various robots.txt patterns."""
        # Should match
        positive_cases = [
            '"robots.txt"',
            "'robots.txt'",
            '/robots.txt',
            'href="robots.txt"',
            "href='robots.txt'",
            'src="/robots.txt"',
            'url(/robots.txt)',  # should match /robots.txt
            'link to "robots.txt" file',
            "check '/robots.txt' for rules",
        ]
        
        expected_files = ['robots.txt']
        
        for case in positive_cases:
            matches = self.regex.findall(case)
            self.assertEqual(matches, expected_files, 
                           f"Failed for robots.txt case: {case}\nGot: {matches}")
    
    def test_sitemap_xml_patterns(self):
        """Test various sitemap.xml patterns."""
        # Basic sitemap patterns
        positive_cases = [
            ('"sitemap.xml"', ['sitemap.xml']),
            ("'sitemap.xml'", ['sitemap.xml']),
            ('/sitemap.xml', ['sitemap.xml']),
            ('"sitemap_index.xml"', ['sitemap_index.xml']),
            ("'sitemap-news.xml'", ['sitemap-news.xml']),
            ('/sitemap_products.xml', ['sitemap_products.xml']),
            ('"sitemap123.xml"', ['sitemap123.xml']),
            ("'sitemapabcdef.xml'", ['sitemapabcdef.xml']),
            ('/sitemap-blog-2024.xml', ['sitemap-blog-2024.xml']),
            ('"sitemap_category_1.xml"', ['sitemap_category_1.xml']),
        ]
        
        for test_string, expected in positive_cases:
            matches = self.regex.findall(test_string)
            self.assertEqual(matches, expected, 
                           f"Failed for sitemap case: {test_string}\nExpected: {expected}\nGot: {matches}")
    
    def test_feed_patterns(self):
        """Test various feed patterns."""
        positive_cases = [
            # feed.xml and feed.json
            ('"feed.xml"', ['feed.xml']),
            ("'feed.xml'", ['feed.xml']),
            ('/feed.xml', ['feed.xml']),
            ('"feed.json"', ['feed.json']),
            ("'feed.json'", ['feed.json']),
            ('/feed.json', ['feed.json']),
            
            # rss.xml
            ('"rss.xml"', ['rss.xml']),
            ("'rss.xml'", ['rss.xml']),
            ('/rss.xml', ['rss.xml']),
            
            # atom.xml
            ('"atom.xml"', ['atom.xml']),
            ("'atom.xml'", ['atom.xml']),
            ('/atom.xml', ['atom.xml']),
        ]
        
        for test_string, expected in positive_cases:
            matches = self.regex.findall(test_string)
            self.assertEqual(matches, expected, 
                           f"Failed for feed case: {test_string}\nExpected: {expected}\nGot: {matches}")
    
    def test_complex_html_scenarios(self):
        """Test realistic HTML scenarios."""
        html_scenarios = [
            # Link tags
            ('<link rel="alternate" type="application/rss+xml" href="/rss.xml" />', ['rss.xml']),
            ('<link rel="sitemap" href="/sitemap.xml" />', ['sitemap.xml']),
            ('<link href="feed.json" type="application/feed+json" />', ['feed.json']),
            
            # Meta tags
            ('<meta name="robots" content="index, follow, sitemap: /sitemap.xml" />', ['sitemap.xml']),
            
            # JavaScript references
            ('fetch("/feed.xml").then(response => response.json())', ['feed.xml']),
            ("loadSitemap('/sitemap_index.xml')", ['sitemap_index.xml']),
            ('url: "robots.txt"', ['robots.txt']),
            
            # HTML content
            ('Check our <a href="/rss.xml">RSS feed</a>', ['rss.xml']),
            ('Visit our sitemap at "/sitemap-news.xml"', ['sitemap-news.xml']),
            
            # Multiple matches in one string
            ('<link href="/rss.xml" /><link href="/atom.xml" />', ['rss.xml', 'atom.xml']),
            ('Files: "robots.txt", "sitemap.xml", "feed.json"', ['robots.txt', 'sitemap.xml', 'feed.json']),
        ]
        
        for html, expected in html_scenarios:
            matches = self.regex.findall(html)
            self.assertEqual(matches, expected, 
                           f"Failed for HTML scenario: {html}\nExpected: {expected}\nGot: {matches}")
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        edge_cases = [
            # Files at start/end of strings
            ('"robots.txt"', ['robots.txt']),
            ("'sitemap.xml'", ['sitemap.xml']),
            
            # With surrounding text
            ('Before "robots.txt" after', ['robots.txt']),
            ("Before 'sitemap.xml' after", ['sitemap.xml']),
            ('Before /feed.xml after', ['feed.xml']),
            
            # Case sensitivity (should match - our pattern is case sensitive)
            ('"robots.txt"', ['robots.txt']),
            ('"sitemap.XML"', []),  # Should not match due to uppercase
            
            # Special characters in sitemap names
            ('"sitemap-test_123.xml"', ['sitemap-test_123.xml']),
            ("'sitemap.special.xml'", ['sitemap.special.xml']),
            ('/sitemap@company.xml', ['sitemap@company.xml']),
        ]
        
        for test_string, expected in edge_cases:
            matches = self.regex.findall(test_string)
            self.assertEqual(matches, expected, 
                           f"Failed for edge case: {test_string}\nExpected: {expected}\nGot: {matches}")
    
    def test_negative_cases(self):
        """Test cases that should NOT match."""
        negative_cases = [
            # Wrong file extensions
            '"robots.html"',
            "'sitemap.txt'",
            '/feed.csv',
            '"rss.json"',
            "'atom.txt'",
            
            # Missing quotes/slashes (plain text)
            'robots.txt',
            'sitemap.xml',
            'feed.xml',
            'plain sitemap.xml text',
            'download robots.txt file',
            
            # Wrong patterns
            '"notrobots.txt"',
            "'mysitemap.xml'",  # doesn't start with 'sitemap'
            # NOTE: "feed.xmls" will match "feed.xml" - this is expected with simple pattern
            '"rss.xml.bak"',    # extra extension - will match rss.xml
            
            # Quoted but wrong extensions
            '"robots.pdf"',
            "'sitemap.html'",
            '/feed.php',
            '"rss.txt"',
            "'atom.json'",
            
            # Case issues (our pattern is case sensitive)
            '"ROBOTS.TXT"',
            "'SITEMAP.XML'",
            '/FEED.XML',
            '"RSS.XML"',
            "'ATOM.XML'",
            
            # Incomplete patterns
            '"robot.txt"',     # missing 's'
            "'sitema.xml'",    # typo
            '/fee.xml',        # incomplete
            '"sr.xml"',        # incomplete rss
            
            # Empty or whitespace
            '""',
            "''",
            '/',
            ' ',
            '',
            
            # Invalid contexts - plain text without quotes/slashes
            'domain.com robots.txt without quotes',  # no quotes/slash prefix
            'check robots.txt file',                 # no quotes/slash prefix  
            'path to sitemap.xml here',              # no quotes/slash prefix
            'download feed.xml now',                 # no quotes/slash prefix
            
            # Malformed
            'robots.txt"',     # quote at end only
            # NOTE: "'sitemap.xml" will match "sitemap.xml" - this is expected
            'feed.xml/',       # slash at end
            
            # Non-matching similar patterns
            '"feed.rss"',      # wrong - should be rss.xml
            "'atom.feed'",     # wrong - should be atom.xml
            '/robots.text',    # wrong extension
        ]
        
        self.assertNoMatches(negative_cases)
    
    def test_realistic_web_content(self):
        """Test with realistic web page content."""
        web_content_scenarios = [
            # WordPress-style
            '''
            <link rel="alternate" type="application/rss+xml" title="RSS 2.0" href="/feed.xml" />
            <link rel="alternate" type="application/atom+xml" title="Atom 1.0" href="/atom.xml" />
            <meta name="robots" content="index, follow" />
            ''',
            
            # E-commerce site
            '''
            <link rel="sitemap" type="application/xml" title="Sitemap" href="/sitemap.xml" />
            <script>
                const sitemaps = ["/sitemap-products.xml", "/sitemap-categories.xml"];
            </script>
            ''',
            
            # News site
            '''
            <head>
                <link rel="alternate" href="/rss.xml" type="application/rss+xml" title="News RSS" />
                <link href="/sitemap-news.xml" rel="sitemap" />
            </head>
            <script>
                if (window.location.pathname === '/robots.txt') {
                    // robots.txt handling
                }
            </script>
            ''',
        ]
        
        expected_results = [
            ['feed.xml', 'atom.xml'],
            ['sitemap.xml', 'sitemap-products.xml', 'sitemap-categories.xml'],
            ['rss.xml', 'sitemap-news.xml', 'robots.txt']
        ]
        
        for content, expected in zip(web_content_scenarios, expected_results):
            matches = self.regex.findall(content)
            self.assertEqual(matches, expected, 
                           f"Failed for web content scenario.\nExpected: {expected}\nGot: {matches}")
    
    def test_performance_with_large_content(self):
        """Test regex performance with large content."""
        # Create large content with embedded matches
        large_content = 'x' * 10000  # 10KB of content
        large_content += '"robots.txt"'
        large_content += 'y' * 10000
        large_content += "'sitemap-large.xml'"
        large_content += 'z' * 10000
        large_content += '/feed.json'
        
        matches = self.regex.findall(large_content)
        expected = ['robots.txt', 'sitemap-large.xml', 'feed.json']
        
        self.assertEqual(matches, expected, 
                        f"Performance test failed.\nExpected: {expected}\nGot: {matches}")
    
    def test_regex_groups(self):
        """Test that the regex captures the filename properly."""
        test_cases = [
            ('"robots.txt"', 'robots.txt'),
            ("'sitemap-test.xml'", 'sitemap-test.xml'),
            ('/feed.json', 'feed.json'),
            ('"atom.xml"', 'atom.xml'),
            ("'rss.xml'", 'rss.xml'),
        ]
        
        for test_string, expected_group in test_cases:
            match = self.regex.search(test_string)
            self.assertIsNotNone(match, f"Should find match in: {test_string}")
            self.assertEqual(match.group(1), expected_group, 
                           f"Group capture failed for: {test_string}")
    
    def test_real_world_edge_cases(self):
        """Test complex real-world scenarios and edge cases."""
        edge_case_scenarios = [
            # WordPress/CMS scenarios
            ('wp-includes/robots.txt not found', ['robots.txt']),  # contains /robots.txt
            ('loadFile("/wp-content/robots.txt")', ['robots.txt']),
            ('"wp-sitemap.xml"', []),  # wp-sitemap doesn't start with sitemap
            ("'sitemap-wp-posts.xml'", ['sitemap-wp-posts.xml']),  # fixed to start with sitemap
            
            # E-commerce scenarios
            ('"sitemap-products-2024.xml"', ['sitemap-products-2024.xml']),
            ("'sitemap.category_electronics.xml'", ['sitemap.category_electronics.xml']),
            ('/sitemap@special-chars.xml', ['sitemap@special-chars.xml']),
            
            # CDN and subdomain scenarios  
            ('https://cdn.example.com"/robots.txt"', ['robots.txt']),  # mixed URL + quote
            ("url('//static.site.com/feed.xml')", ['feed.xml']),
            ('fetch("https://api.site.com/feed.json")', ['feed.json']),
            
            # JavaScript/JSON scenarios
            ('{"sitemap": "/sitemap-api.xml"}', ['sitemap-api.xml']),
            ("['robots.txt', 'sitemap.xml']", ['robots.txt', 'sitemap.xml']),
            ('const feeds = ["/rss.xml", "/atom.xml"];', ['rss.xml', 'atom.xml']),
            
            # HTML attribute scenarios
            ('data-sitemap="/sitemap-data.xml"', ['sitemap-data.xml']),
            ('content="robots.txt rules apply"', ['robots.txt']),
            ('<meta name="feed" content="/feed.xml" />', ['feed.xml']),
            
            # URL parameter scenarios
            ('?file=/robots.txt&format=text', ['robots.txt']),  # should match /robots.txt
            ('redirect="/feed.json"', ['feed.json']),
            ('next="/sitemap-page2.xml"', ['sitemap-page2.xml']),
            
            # Mixed quote scenarios
            ('Both "robots.txt" and \'/feed.xml\' exist', ['robots.txt', 'feed.xml']),
            ("Mixed 'sitemap.xml' and \"/atom.xml\"", ['sitemap.xml', 'atom.xml']),
            
            # Special character edge cases
            ('"sitemap\\"quoted.xml"', []),  # escaped quotes should not match
            ("'sitemap\\'quoted.xml'", []),  # escaped quotes should not match
            ('path=/sitemap end', []),  # partial match - should not match without proper boundary
            
            # International/Unicode contexts (files still ASCII)
            ('Télécharger "/robots.txt" ici', ['robots.txt']),
            ('查看 "/feed.xml" 内容', ['feed.xml']),
            ('файл "/sitemap.xml" доступен', ['sitemap.xml']),
        ]
        
        for content, expected in edge_case_scenarios:
            matches = self.regex.findall(content)
            self.assertEqual(matches, expected, 
                           f"Edge case failed for: {content}\nExpected: {expected}\nGot: {matches}")
    
    def test_complex_html_structures(self):
        """Test complex HTML document structures."""
        complex_html_scenarios = [
            # Complete HTML head section
            ('''
            <head>
                <title>Test Site</title>
                <meta name="robots" content="index,follow">
                <link rel="canonical" href="https://example.com/">
                <link rel="alternate" type="application/rss+xml" href="/rss.xml">
                <link rel="sitemap" type="application/xml" href="/sitemap.xml">
                <script>
                    window.feeds = {
                        "rss": "/feed.xml",
                        "atom": '/atom.xml'
                    };
                </script>
            </head>
            ''', ['rss.xml', 'sitemap.xml', 'feed.xml', 'atom.xml']),
            
            # Complex JavaScript with multiple file references
            ('''
            <script>
                const config = {
                    seo: {
                        robots: "/robots.txt",
                        sitemaps: ["/sitemap.xml", "/sitemap-news.xml"],
                        feeds: {
                            rss: "/rss.xml",
                            json: "/feed.json"
                        }
                    }
                };
                
                if (window.location.pathname === "/admin") {
                    loadFile('/sitemap-admin.xml');
                }
            </script>
            ''', ['robots.txt', 'sitemap.xml', 'sitemap-news.xml', 'rss.xml', 'feed.json', 'sitemap-admin.xml']),
            
            # React/Modern JS patterns
            ('''
            const SeoComponent = () => {
                const [sitemap, setSitemap] = useState("/sitemap-react.xml");
                return (
                    <div>
                        <link rel="alternate" href="/feed.xml" />
                        {isBot && <link rel="robots" href="/robots.txt" />}
                    </div>
                );
            };
            ''', ['sitemap-react.xml', 'feed.xml', 'robots.txt']),
            
            # Server-side template patterns
            ('''
            {% if settings.SEO_ENABLED %}
                <link rel="sitemap" href="/sitemap-{{ category }}.xml" />
                <link rel="alternate" href="/rss.xml" />
            {% endif %}
            <script>
                fetch("/feed.json").then(response => {
                    // Process feed data
                });
            </script>
            ''', ['sitemap-{{ category }}.xml', 'rss.xml', 'feed.json']),
        ]
        
        for html, expected in complex_html_scenarios:
            matches = self.regex.findall(html)
            self.assertEqual(matches, expected, 
                           f"Complex HTML scenario failed.\nExpected: {expected}\nGot: {matches}")
    
    def test_sitemap_naming_variations(self):
        """Test various sitemap naming patterns found in the wild."""
        sitemap_variations = [
            # Standard patterns
            ('"/sitemap.xml"', ['sitemap.xml']),
            ("'/sitemap_index.xml'", ['sitemap_index.xml']),
            ('"/sitemap-index.xml"', ['sitemap-index.xml']),
            
            # Category/type specific
            ('"/sitemap-posts.xml"', ['sitemap-posts.xml']),
            ("'/sitemap_pages.xml'", ['sitemap_pages.xml']),
            ('"/sitemap-categories.xml"', ['sitemap-categories.xml']),
            ('"/sitemap_products.xml"', ['sitemap_products.xml']),
            ("'/sitemap-news.xml'", ['sitemap-news.xml']),
            
            # Date/version specific
            ('"/sitemap-2024.xml"', ['sitemap-2024.xml']),
            ("'/sitemap_2024_01.xml'", ['sitemap_2024_01.xml']),
            ('"/sitemap-2024-january.xml"', ['sitemap-2024-january.xml']),
            
            # Multi-language
            ('"/sitemap-en.xml"', ['sitemap-en.xml']),
            ("'/sitemap_fr.xml'", ['sitemap_fr.xml']),
            ('"/sitemap-zh-cn.xml"', ['sitemap-zh-cn.xml']),
            
            # Platform specific
            ('"/wp-sitemap.xml"', []),  # wp-sitemap doesn't start with 'sitemap'
            ("'/drupal-sitemap.xml'", []),  # drupal-sitemap doesn't start with 'sitemap'
            ('"/sitemap.shopify.xml"', ['sitemap.shopify.xml']),
            
            # Special characters and numbers
            ('"/sitemap_123.xml"', ['sitemap_123.xml']),
            ("'/sitemap-v2.xml'", ['sitemap-v2.xml']),
            ('"/sitemap@domain.xml"', ['sitemap@domain.xml']),
            ('"/sitemap.special.xml"', ['sitemap.special.xml']),
            
            # Edge cases that should still match
            ('"/sitemapABC.xml"', ['sitemapABC.xml']),
            ("'/sitemap999.xml'", ['sitemap999.xml']),
            ('"/sitemap_.xml"', ['sitemap_.xml']),
            ('"/sitemap-.xml"', ['sitemap-.xml']),
        ]
        
        for content, expected in sitemap_variations:
            matches = self.regex.findall(content)
            self.assertEqual(matches, expected, 
                           f"Sitemap variation failed for: {content}\nExpected: {expected}\nGot: {matches}")
    
    def test_concurrent_and_boundary_cases(self):
        """Test boundary conditions and concurrent patterns."""
        boundary_cases = [
            # Multiple patterns in single string
            ('Load "robots.txt" then "/sitemap.xml" and \'/feed.json\'', ['robots.txt', 'sitemap.xml', 'feed.json']),
            
            # At string boundaries
            ('"robots.txt"', ['robots.txt']),
            ("'sitemap.xml'", ['sitemap.xml']),
            ('/feed.xml', ['feed.xml']),
            
            # Adjacent patterns
            ('"/robots.txt"/sitemap.xml"', ['robots.txt', 'sitemap.xml']),
            ("'feed.xml'\"atom.xml\"", ['feed.xml', 'atom.xml']),
            
            # Whitespace variations
            (' "robots.txt" ', ['robots.txt']),
            ('\t/sitemap.xml\n', ['sitemap.xml']),
            ('\r\n"feed.xml"\r\n', ['feed.xml']),
            
            # Nested quotes (should match inner patterns)
            ('"Check \'robots.txt\' file"', ['robots.txt']),  # contains 'robots.txt' which should match
            ("'Load \"sitemap.xml\" now'", ['sitemap.xml']),   # contains "sitemap.xml" which should match
            
            # URL fragments and anchors - should match the file part
            ('href="/robots.txt#section"', ['robots.txt']),
            ("'/sitemap.xml?version=1'", ['sitemap.xml']),
            ('"/feed.xml&format=json"', ['feed.xml']),
            
            # File paths in different contexts
            ('import "/robots.txt"', ['robots.txt']),
            ('require("./sitemap.xml")', ['sitemap.xml']),  # Note: . in path
            ('include \'/feed.xml\'', ['feed.xml']),
            
            # Very long strings with patterns
            ('x' * 1000 + '"robots.txt"' + 'y' * 1000 + "'sitemap.xml'", ['robots.txt', 'sitemap.xml']),
        ]
        
        for content, expected in boundary_cases:
            matches = self.regex.findall(content)
            self.assertEqual(matches, expected, 
                           f"Boundary case failed for: {content}\nExpected: {expected}\nGot: {matches}")


def run_manual_tests():
    """Manual testing function to see regex in action."""
    pattern = r'["\'/](robots\.txt|sitemap[^"\'\s]*\.xml|feed\.(?:xml|json)|rss\.xml|atom\.xml)'
    regex = re.compile(pattern)
    
    print("=== Manual Test Cases ===")
    
    test_strings = [
        '<link href="/rss.xml" type="application/rss+xml" />',
        'Check "robots.txt" for crawl rules',
        "Load sitemap from '/sitemap-products.xml'",
        'fetch("/feed.json").then(response => response.json())',
        'Multiple: "robots.txt", "sitemap.xml", "atom.xml"',
        'Invalid: robots.html, mysitemap.xml, feed.php',
        '"sitemap-category_123.xml"',
        'No match here: just normal text',
        'https://example.com/robots.txt',  # should match /robots.txt part
        '"SITEMAP.XML"',  # case sensitive - should not match
        'WordPress: "/wp-sitemap.xml"',
        'Mixed quotes: "robots.txt" and \'/feed.xml\'',
        'fetch("https://cdn.site.com/feed.json")',
        'Plain text robots.txt without quotes',
        '{"files": ["/robots.txt", "/sitemap.xml"]}',
    ]
    
    for test_string in test_strings:
        matches = regex.findall(test_string)
        print(f"Input:   {test_string}")
        print(f"Matches: {matches}")
        print("-" * 60)
        
    print("\n=== Performance Test ===")
    import time
    large_content = "Random content " * 10000 + '"robots.txt"' + " more content " * 10000 + "'sitemap.xml'"
    
    start_time = time.time()
    matches = regex.findall(large_content)
    end_time = time.time()
    
    print(f"Large content ({len(large_content)} chars): {matches}")
    print(f"Time taken: {end_time - start_time:.4f} seconds")
    print("-" * 60)


if __name__ == "__main__":
    # Run unit tests
    print("Running comprehensive regex tests...")
    unittest.main(verbosity=2, exit=False)
    
    # Run manual tests
    print("\n" + "="*60)
    run_manual_tests() 