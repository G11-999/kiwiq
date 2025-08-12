import re
import uuid
from bs4 import BeautifulSoup
import trafilatura
from workflow_service.services.scraping.utils.markdown_converter import convert_to_markdown_from_raw_file_content


def clean_html_text_and_convert_to_markdown(html: str, remove_links: bool = True) -> str:
    """
    Clean HTML text and convert to markdown.
    """

    # Pre-process to protect headings
    soup = BeautifulSoup(html, 'html.parser')
    
    # Store original headings
    heading_map = {}
    for i, heading in enumerate(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])):
        text = heading.get_text(strip=True)
        text_uuid = uuid.uuid5(uuid.NAMESPACE_URL, text)
        placeholder = f"HEADING_PLACEHOLDER_{i}_{text_uuid}"
        heading_map[placeholder] = {
            'tag': heading.name,
            'text': text,
            'html': str(heading)
        }
        # Replace heading with a paragraph containing placeholder
        new_tag = soup.new_tag('p')
        new_tag.string = placeholder  # f"{placeholder}: {text}"
        heading.replace_with(new_tag)
    
    # Extract with trafilatura
    output = trafilatura.extract(
        str(soup),
        output_format="html",
        include_formatting=True,
        include_links=True,
        favor_recall=True,
        include_comments=True
    )

    # Restore headings
    if output:
        for placeholder, heading_info in heading_map.items():
            # Replace placeholder with original heading HTML
            output = output.replace(
                f"<p>{placeholder}</p>",  # f"<p>{placeholder}: {heading_info['text']}</p>"
                heading_info['html']
            )
            # Also handle case where <p> tags were stripped
            output = output.replace(
                f"{placeholder}",  # f"{placeholder}: {heading_info['text']}",
                heading_info['html']
            )

    # output = trafilatura.extract(html, output_format="html", include_formatting=True, include_links=True, favor_recall=True, include_comments=True, )
    # output = trafilatura.bare_extraction(html, as_dict=True, include_formatting=True, include_links=True, favor_recall=True, include_comments=True, )
    # print(output)
    # import ipdb; ipdb.set_trace()
    
    cleaned_markdown_content = convert_to_markdown_from_raw_file_content(output, f"temp_{uuid.uuid4()}.html")

    if remove_links:
        cleaned_markdown_content = remove_markdown_links(cleaned_markdown_content, max_chars=None)

    return cleaned_markdown_content


def remove_markdown_links(text: str, max_chars: int | None = None) -> str:
    """
    Remove markdown links from text while retaining the bracketed link text.

    This strips the URL portion of markdown links while preserving the link
    label wrapped in brackets. For example, "[Example](https://x.com)"
    becomes "[Example]".

    Args:
        text: The markdown text containing links.
        max_chars: Optional maximum characters to retain from the link text.
            When provided and the link text exceeds this length, the text is
            truncated and an ellipsis is appended within the brackets.

    Returns:
        Text with markdown links removed and link text preserved in brackets.
    """

    def replace_link(match: re.Match[str]) -> str:
        link_text: str = match.group(1)
        if max_chars is not None and len(link_text) > max_chars:
            # Truncate and add ellipsis if text is longer than max_chars, keep brackets
            return f"[{link_text[:max_chars]}...]"
        return f"[{link_text}]"
    
    # Pattern to match markdown links: [text](url)
    # Using non-greedy matching (*?) to avoid matching multiple links
    pattern = r'\[([^\]]*?)\]\([^\)]*?\)'
    
    # Replace all markdown links with just the text part
    result = re.sub(pattern, replace_link, text)
    
    return result


def remove_markdown_links_advanced(
    text: str,
    max_chars: int | None = None,
    placeholder: str = "",
) -> str:
    """
    Advanced version with more options for handling markdown links, keeping
    the link text wrapped in brackets after cleanup.

    Args:
        text: The markdown text containing links.
        max_chars: Optional maximum characters to retain from link text. If
            provided and exceeded, the text is truncated (accounting for
            ellipsis) and preserved inside brackets.
        placeholder: Text to use inside the brackets if link text is empty.

    Returns:
        Text with markdown links processed and link text preserved in brackets.
    """

    def replace_link(match: re.Match[str]) -> str:
        link_text: str = match.group(1).strip()

        # Handle empty link text
        if not link_text:
            return f"[{placeholder}]"

        if max_chars is not None and len(link_text) > max_chars:
            if max_chars <= 3:
                # If max_chars is very small, just truncate (no ellipsis), keep brackets
                return f"[{link_text[:max_chars]}]"
            else:
                # Add ellipsis for longer truncations, keep brackets
                return f"[{link_text[: max_chars - 3]}...]"
        return f"[{link_text}]"
    
    # Pattern for inline links [text](url) - using non-greedy matching
    pattern_inline = r'\[([^\]]*?)\]\([^\)]*?\)'
    result = re.sub(pattern_inline, replace_link, text)
    
    # # Remove reference definitions [ref]: url
    # pattern_ref_def = r'^\[[^\]]+?\]:\s+.+?$'
    # result = re.sub(pattern_ref_def, '', result, flags=re.MULTILINE)
    
    # Convert reference-style links [text][ref] to just text
    pattern_ref_link = r'\[([^\]]+?)\]\[[^\]]*?\]'
    result = re.sub(pattern_ref_link, r'[\1]', result)
    
    # Clean up any extra blank lines
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result.strip()


# Example usage
if __name__ == "__main__":
    # Test text with various markdown links
    markdown_text = """
    This is a [sample link](https://example.com) in markdown.
    Here's another [very long link text that might need truncation](https://google.com).
    And [another one](https://github.com) with more text.
    
    Some text with [](https://empty-text.com) empty link text.
    
    Reference style: [Reference link][1] and [Another ref][2].
    
    Multiple links close together: [first](url1)[second](url2)[third](url3)
    
    [1]: https://reference1.com
    [2]: https://reference2.com
    """
    
    # print("Original text:")
    # print(markdown_text)
    # print("\n" + "="*50 + "\n")
    
    # # Remove links, keep all text
    # print("Links removed (keep all text):")
    # print(remove_markdown_links(markdown_text))
    # print("\n" + "="*50 + "\n")
    
    # # Remove links, limit text to 10 characters
    # print("Links removed (max 10 chars):")
    # print(remove_markdown_links(markdown_text, max_chars=10))
    # print("\n" + "="*50 + "\n")
    
    # # Advanced version with reference links handling
    # print("Advanced version (max 15 chars):")
    # print(remove_markdown_links_advanced(markdown_text, max_chars=15, placeholder="link"))

    html = """
    
<!DOCTYPE html><!-- Last Published: Fri Aug 08 2025 17:30:26 GMT+0000 (Coordinated Universal Time) --><html data-wf-domain="otterai-website.webflow.io" data-wf-page="685dc56e04613170da497b49" data-wf-site="618e9316785b3582a5178502" lang="en" data-wf-collection="685dc56e04613170da497b33" data-wf-item-slug="active-listening"><head><meta charset="utf-8"/><title>Active Listening: Tips, Techniques, and Examples | Otter.ai</title><meta content="Active listening helps tune out the background noise and tune into your conversations. Here’s how with practical tips, techniques, and examples." name="description"/><meta content="Active Listening: Tips, Techniques, and Examples | Otter.ai" property="og:title"/><meta content="Active listening helps tune out the background noise and tune into your conversations. Here’s how with practical tips, techniques, and examples." property="og:description"/><meta content="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/68627641052699af345971c4_685dc6d2b61ade1efd9b3a0c_679928c91e9ce2c26871220a_active-Listening.jpeg" property="og:image"/><meta content="Active Listening: Tips, Techniques, and Examples | Otter.ai" property="twitter:title"/><meta content="Active listening helps tune out the background noise and tune into your conversations. Here’s how with practical tips, techniques, and examples." property="twitter:description"/><meta content="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/68627641052699af345971c4_685dc6d2b61ade1efd9b3a0c_679928c91e9ce2c26871220a_active-Listening.jpeg" property="twitter:image"/><meta property="og:type" content="website"/><meta content="summary_large_image" name="twitter:card"/><meta content="width=device-width, initial-scale=1" name="viewport"/><link href="https://cdn.prod.website-files.com/618e9316785b3582a5178502/css/otterai-website.shared.d998a288e.css" rel="stylesheet" type="text/css"/><script type="text/javascript">!function(o,c){var n=c.documentElement,t=" w-mod-";n.className+=t+"js",("ontouchstart"in o||o.DocumentTouch&&c instanceof DocumentTouch)&&(n.className+=t+"touch")}(window,document);</script><link href="https://cdn.prod.website-files.com/618e9316785b3582a5178502/618e94bcbca88b51e2ad81f7_favicon.png" rel="shortcut icon" type="image/x-icon"/><link href="https://cdn.prod.website-files.com/618e9316785b3582a5178502/618e943a80919a98b5e9bf69_apple-icon.png" rel="apple-touch-icon"/><!-- Swiper CSS -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.css"/>

<style>
  body .w-webflow-badge {
  	display: none !important;
  }
</style>

<!-- OneTrust Cookies Consent Notice start for otter.ai -->
<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"  type="text/javascript" charset="UTF-8" data-domain-script="535778f3-6e8c-4a25-847b-26013045c3ac" ></script>
<!-- OneTrust Cookies Consent Notice end for otter.ai -->

<!-- Cookie Utility Script -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/js-cookie/3.0.5/js.cookie.min.js"></script>
<!-- End Cookie Utility Script -->

<!-- Start of statsig stable ID generation - MUST be placed before any statsig scripts -->
<script type="text/javascript">
  !(function getOrGenerateStatSigStableID() {
    try {
      const storageKey = 'statsig.stable_id.2916133601';
      const _getStatSigStableIDFromLocalStorage = () => {
        const value = window.localStorage.getItem(storageKey);
        return value ? JSON.parse(value) : null;
      }
      const _persistStatSigStableIDAsCookie = (stableID) => {
        Cookies.set('statsig_stable_id', stableID, { expires: 365 });
      }
      const sdkStableID = _getStatSigStableIDFromLocalStorage();
      const cookieStableID = Cookies.get('statsig_stable_id') ?? null;
      if (sdkStableID) {
        if (!cookieStableID || sdkStableID === cookieStableID) {
          _persistStatSigStableIDAsCookie(sdkStableID);
        }
        window.otter_statsig_stable_id = sdkStableID;
      } else {
        const stableIDToUse = cookieStableID || crypto.randomUUID();
        _persistStatSigStableIDAsCookie(stableIDToUse);
        window.otter_statsig_stable_id = stableIDToUse;
      }
    } catch (e) {}
  })();
</script>
<!-- End of statsig stable ID generation -->

<!-- Statsig Script -->
<script src="https://cdn.jsdelivr.net/npm/@statsig/js-client@3/build/statsig-js-client+session-replay+web-analytics.min.js?apikey=client-AgfhdSMRmeNqZpTt4cg9ytp2Bch3DskbAomr4586nOD">
</script>
<!-- End Statsig Script -->

<!-- Start of Marketing Website Redesign Experiment Code -->
<script type="text/javascript">
  !(function () {
    try {
      const FEATURE_GATE = "marketing_website_redesign_launch";
      const cohortName = `${FEATURE_GATE}_cohort`;
      const value = Cookies.get(cohortName);
      window.getHomepageExperimentCohort = function () {
        /** naming convention */
        if (value === "enabled") return "Test";
        if (value === "disabled") return "Control";
        return null;
      };
    } catch (e) {}
  })();
</script>
<!-- End of Marketing Website Redesign Experiment Code -->

<!-- Optimizely and Clearbit -->
<script type="text/plain" class="optanon-category-C0002">
  (function () {
    let enableOptimizelyCookieCheck = true;
 
   	if (/^[^:]+:\/\/staging/.exec(window.location.href)) {
      enableOptimizelyCookieCheck = true;
  	}
 
    if (enableOptimizelyCookieCheck) {
      let hasCookie = document.cookie.indexOf("shouldLoadOptimizely") !== -1;
      if (!hasCookie) {
        const cookieExpiry = 30 * 24 * 60 * 60;
        document.cookie = `shouldLoadOptimizely=true; max-age=${cookieExpiry}; SameSite=Lax`;
        console.log("Setting Optimizely cookie to load for Otter Web App");
      } else {
        console.log("Not setting Optimizely cookie since one was already found");
      }
    }
	let optimizelyLoadAttempt = 0;
    var clearbitScriptEl = document.createElement("script");
    clearbitScriptEl.type = "text/javascript";
    document.head.appendChild(clearbitScriptEl);
    clearbitScriptEl.onload = function () {
      console.log('Clearbit has loaded, will load Optimizely next');
      var optimizelyInterval = setInterval(() => {
		if (optimizelyLoadAttempt === 5) {
          clearInterval(optimizelyInterval);
		  optimizelyLoadAttempt = 0;
		  console.error('Exhausted 5 attempts to load Optimizely, exiting now');
          return;
		}

        if (window.reveal) {
          clearInterval(optimizelyInterval);
		  optimizelyLoadAttempt = 0;
          var optimizelyScriptEl = document.createElement("script");
          optimizelyScriptEl.type = "text/javascript";
          document.head.appendChild(optimizelyScriptEl);
          optimizelyScriptEl.src =
            "https://cdn.optimizely.com/js/23241510302.js";
        } else {
          optimizelyLoadAttempt++;
		}
      }, 100);
    };
    clearbitScriptEl.src =
      "https://tag.clearbitscripts.com/v1/pk_2b13f54f743de7cc7b292707f96a4bbe/tags.js";
  })();
</script>

<!-- Google Tag manager -->
<script type="text/javascript">(function (w, d, s, l, i) {
  w[l] = w[l] || [];
  w[l].push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' });
  const f = d.getElementsByTagName(s)[0];
  const j = d.createElement(s);
  const dl = l != 'dataLayer' ? '&l=' + l : '';
  j.setAttribute('async', 'true');
  j.setAttribute('src', `https://www.googletagmanager.com/gtm.js?id=${i}${dl}`);
  d.head.appendChild(j);
})(window, document, 'script', 'dataLayer', 'GTM-M866M5H');</script>
<!-- End Google Tag manager -->

<script type="text/javascript" src="https://www.googletagmanager.com/gtag/js?id=G-F0G9HT49XE"></script>
<script type="text/javascript"
        >
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-F0G9HT49XE');
</script>

<!-- Amplitude -->
<script type="text/javascript">

  /** retrieves the user properties associated with the redesign for tracking */
  function getHomeCohortEventProperties() {
    try {
      if (!window.getHomepageExperimentCohort) return {};
      const cohort = window.getHomepageExperimentCohort()
      if (!cohort) return {};
      return { HomePageVariant: cohort };
    } catch (e) {
      return {};
    }
  }

!function(){"use strict";!function(e,t){var r=e.amplitude||{_q:[],_iq:[]};if(r.invoked)e.console&&console.error&&console.error("Amplitude snippet has been loaded.");else{var n=function(e,t){e.prototype[t]=function(){return this._q.push({name:t,args:Array.prototype.slice.call(arguments,0)}),this}},s=function(e,t,r){return function(n){e._q.push({name:t,args:Array.prototype.slice.call(r,0),resolve:n})}},o=function(e,t,r){e[t]=function(){if(r)return{promise:new Promise(s(e,t,Array.prototype.slice.call(arguments)))}}},i=function(e){for(var t=0;t<m.length;t++)o(e,m[t],!1);for(var r=0;r<y.length;r++)o(e,y[r],!0)};r.invoked=!0;var a=t.createElement("script");a.type="text/javascript",a.integrity="sha384-PPfHw98myKtJkA9OdPBMQ6n8yvUaYk0EyUQccFSIQGmB05K6aAMZwvv8z50a5hT2",a.crossOrigin="anonymous",a.async=!0,a.src="https://cdn.amplitude.com/libs/marketing-analytics-browser-0.3.2-min.js.gz",a.onload=function(){e.amplitude.runQueuedFunctions||console.log("[Amplitude] Error: could not load SDK")};var c=t.getElementsByTagName("script")[0];document.head.appendChild(a);for(var u=function(){return this._q=[],this},p=["add","append","clearAll","prepend","set","setOnce","unset","preInsert","postInsert","remove","getUserProperties"],l=0;l<p.length;l++)n(u,p[l]);r.Identify=u;for(var d=function(){return this._q=[],this},v=["getEventProperties","setProductId","setQuantity","setPrice","setRevenue","setRevenueType","setEventProperties"],f=0;f<v.length;f++)n(d,v[f]);r.Revenue=d;var m=["getDeviceId","setDeviceId","getSessionId","setSessionId","getUserId","setUserId","setOptOut","setTransport","reset"],y=["init","add","remove","track","logEvent","identify","groupIdentify","setGroup","revenue","flush"];i(r),r.createInstance=function(){var e=r._iq.push({_q:[]})-1;return i(r._iq[e]),r._iq[e]},e.amplitude=r}}(window,document)}();
amplitude.add({
  type: "enrichment",
  setup: function(){ return Promise.resolve(); },
  execute: function(evt){
    evt.platform = 'Web';
    try {
      if (evt.event_type === 'Page View') {
        evt.event_type = 'WebPageView';
        const homeCohortProperties = getHomeCohortEventProperties();
        var url = new URL(evt.event_properties.page_location);
        evt.event_properties = {
          ...evt.event_properties,
          origin: url.origin,
          path: evt.event_properties.page_path,
          search: url.search,
          ...homeCohortProperties
        };        
      }
    } catch (err) {}
    return Promise.resolve(evt);
  }
});
  
var amplitudeApiKey = "1edd6ec91d887d8778846bbb67d6db08";

if (/^[^:]+:\/\/staging/.exec(window.location.href) || /^[^:]+:\/\/home/.exec(window.location.href)) {
    amplitudeApiKey = "462d68bea713b4e24a17e79d9b2b2abf";
  }
  
amplitude.init(amplitudeApiKey, undefined, {
  pageViewTracking: true
});
</script>
<!-- End Amplitude -->

<!-- StatSig init and checkGate -->
<script>
  const HOMEPAGE_GATE = 'marketing_website_redesign_launch';
  var statsig_client;
  
  function handleButtonChanges(buttonIds) {
    for (id of buttonIds) {
        document.getElementById(id).onclick = function() {
          window.location.href = `${window.location.origin}${window.location.pathname}-demo`;
        }
	}
  }

  /** retrieves the user properties associated with the redesign for tracking */
  function getHomeCohortUserProperties() {
    try {
      if (!window.getHomepageExperimentCohort) return {};
      const cohort = window.getHomepageExperimentCohort()
      if (!cohort) return {};
      return { [`${HOMEPAGE_GATE}_cohort`]: cohort };
    } catch (e) {
      return {};
    }
  }
  
  document.addEventListener('DOMContentLoaded', async () => {
    var env = "production";
    if (/^[^:]+:\/\/staging/.exec(window.location.href) || /^[^:]+:\/\/home/.exec(window.location.href)) {
      env = "staging";
    }
    var options = {
      environment: { tier: env },
    };
    const homeCohortProperties = getHomeCohortUserProperties();
    const stableIDOverride = window.otter_statsig_stable_id || null;
    statsig_client = new window.__STATSIG__.StatsigClient("client-AgfhdSMRmeNqZpTt4cg9ytp2Bch3DskbAomr4586nOD", { 
      custom: { ...homeCohortProperties },
      ...(stableIDOverride && { customIDs: { stableID: stableIDOverride } }),
    }, options);
    await statsig_client.initializeAsync();
    
    const stableID = statsig_client.getContext().stableID;
    
    let redirectURL = `https://staging.otter.ai/live-demo`
    if (env === 'production') {
      redirectURL = `https://otter.ai/live-demo`
    }
    
    const pathName = window.location.pathname
    const params = ["auto=true", "embed=true", "name_popup=true"]
    
    if (stableID) {
      params.push(`statsig_stable_id=${stableID}`)
    }
    
    params.push(`utm_campaign=${pathName === '/' ? 'home' : pathName.slice(1)}`)
    
    const urlParams = `?${params.join("&")}` 
    
    // Setting the Amplitude properties.
    const identify = new amplitude.Identify();
    identify.set("statsig_stable_id", stableID);

    // This is the id of the div that has "Start for Free" and "See Live Demo" btns on the old page.
    const homepageBtnContainer = document.querySelectorAll('[data-primary-buttons]');
      
    homepageBtnContainer.forEach((button, index) => {
      const startForFreeActionBtn = button.querySelector('[data-button-start]');
      const seeLiveDemoActionBtn = button.querySelector('[data-button-demo]')
      
      if (startForFreeActionBtn) {
        startForFreeActionBtn.style.visibility = 'visible'
        startForFreeActionBtn.style.display = 'flex'
      }
      
      if (seeLiveDemoActionBtn) {
          seeLiveDemoActionBtn.innerHTML = 'Demo it Live'
          seeLiveDemoActionBtn.style.visibility = "visible"
          seeLiveDemoActionBtn.style.display = "flex"
          seeLiveDemoActionBtn.onclick = () => {
            seeLiveDemoActionBtn.style.pointerEvents = "none";
            setTimeout(() => {
              seeLiveDemoActionBtn.style.pointerEvents = "auto";
              window.location.href = redirectURL + urlParams
            },0)
          };
      }
  	});
    
    // This btn is in the Nav bar
    const scheduleDemoActionBtn = document.getElementById('schedule-demo-btn')
    if (scheduleDemoActionBtn) {
      scheduleDemoActionBtn.style.display = "flex";
    }
    
    // If we are already on the demo page, do not show the Schedule a Demo btn.
    if (pathName.includes('demo') && scheduleDemoActionBtn) {
      scheduleDemoActionBtn.style.display = "none";
    }

    const scheduleDemoActionBtnLinks = {
      "/recruiting-agent": '/demo',
      "/media-agent": '/media-teams-demo',
      "/media-teams": '/media-teams-demo',
      "/education-agent": '/education-demo',
      "/education": '/education-demo',
      "/business": '/business-demo',
      "/sales-agent": '/sales-teams-demo',
      "/sales-teams": '/sales-teams-demo',
      "/pricing": "/pricing-demo",
      "/product-teams": "/product-teams-demo"
    }

    function handleRedirectionFromNavBar(pathName) {
      if (pathName) {
      	if (scheduleDemoActionBtnLinks[pathName]) {
          // This is the case where the pathname belongs to the special path names list.
          window.location.href = `${window.location.origin}${scheduleDemoActionBtnLinks[pathName]}`;
        } else {
          // If the pathname is eg. /individuals, this will redirect to https://home.otter.ai/general-demo?utm_content=see_demo
          window.location.href = `${window.location.origin}/demo`;
          //window.location.href = `${window.location.origin}/general-demo`;
        }
      }
    }

    // This block of code only handles the button that we see on the Nav bar.
    scheduleDemoActionBtn.onclick = () => handleRedirectionFromNavBar(pathName)
    
    // This block of code handles the logic where there are multiple demo buttons on certain pages.
    if (scheduleDemoActionBtnLinks[pathName]) {
      switch (pathName) {
        case '/business':
          handleButtonChanges(['demo1-business', 'demo2-business', 'demo-enterprise'])
          break;
        case '/education':
          handleButtonChanges(['demo1-education', 'demo2-education'])
          break;
        case '/product-teams':
          handleButtonChanges(['demo1-product-teams', 'demo2-product-teams', 'demo-enterprise'])
          break;
        case '/sales-teams':
          handleButtonChanges(['demo1-sales-teams'])
          break;
        case '/media-teams':
          handleButtonChanges(['demo1-media-teams', 'demo2-media-teams', 'demo-enterprise'])
          break;
        case '/pricing':
          handleButtonChanges(['demo1-pricing', 'demo2-pricing'])
          break;
      }
    }

    // Set cohort for marketing website redesign experiment
    if (window.location.pathname === "/") {
      statsig_client.checkGate(HOMEPAGE_GATE);
      for (const [key, value] of Object.entries(homeCohortProperties)) {
        identify.set(key, value);
      }
    }
    
    // BEGIN CDN EXPERIMENT
    const gateName = 'use_cdn';
    const gateRes = statsig_client.checkGate(gateName)
    const value = gateRes ? 'enabled' : 'control'
    document.cookie = 'useCdn=' + (gateRes ? 'true' : 'false') + '; max-age=31536000; path=/; domain=otter.ai';
    identify.set(`${gateName}_cohort`, value);
    // END CDN EXPERIMENT
    amplitude.identify(identify);

  })

</script>
<!-- StatSig init and checkGate -->

<script type="text/plain" class="optanon-category-C0002">
	(function () {
	var zi = document.createElement('script');
	zi.type = 'text/javascript';
	zi.async = true;
	zi.referrerPolicy = 'unsafe-url';
	zi.src = 'https://ws.zoominfo.com/pixel/61f17c824827d70015787576';
	document.head.appendChild(zi);
	})();
</script>

<!-- Tatari Pixel -->
<script type="text/plain">
!function(){try{!function(t,i){if(!i.version){window.tatari=i,i.init=function(t,n){var e=function(t,n){i[n]=function(){t.push([n].concat(Array.prototype.slice.call(arguments,0)))}};"track pageview identify".split(" ").forEach(function(t){e(i,t)}),i._i=t,i.config=n,i.pageview()},i.version="1.2.1";var n=t.createElement("script");n.type="text/javascript",n.async=!0,n.src="https://d2hrivdxn8ekm8.cloudfront.net/tag-manager/377ea37d-e187-4eb2-a0eb-597a61c44720-latest.js";var e=t.getElementsByTagName("script")[0];e.parentNode.insertBefore(n,e)}}(document,window.tatari||[])}catch(t){console.log(t)}}(); tatari.init('377ea37d-e187-4eb2-a0eb-597a61c44720');
</script>

<!-- Start of Async Drift Code -->
<script>
"use strict";

!function() {
  var t = window.driftt = window.drift = window.driftt || [];
  if (!t.init) {
    if (t.invoked) return void (window.console && console.error && console.error("Drift snippet included twice."));
    t.invoked = !0, t.methods = [ "identify", "config", "track", "reset", "debug", "show", "ping", "page", "hide", "off", "on" ], 
    t.factory = function(e) {
      return function() {
        var n = Array.prototype.slice.call(arguments);
        return n.unshift(e), t.push(n), t;
      };
    }, t.methods.forEach(function(e) {
      t[e] = t.factory(e);
    }), t.load = function(t) {
      var e = 3e5, n = Math.ceil(new Date() / e) * e, o = document.createElement("script");
      o.type = "text/javascript", o.async = !0, o.crossorigin = "anonymous", o.src = "https://js.driftt.com/include/" + n + "/" + t + ".js";
      var i = document.getElementsByTagName("script")[0];
      i.parentNode.insertBefore(o, i);
    };
  }
}();
drift.SNIPPET_VERSION = '0.3.1';
drift.load('c2ban487bwvc');
</script>
<!-- End of Async Drift Code --><meta name="robots" content="noindex">

<meta name="robots" content="index">
<meta name="language" content="">

<link href="https://otter.ai/blog/active-listening" rel="canonical">

<!-- Global site tag (gtag.js) - Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=UA-93717735-3"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'UA-93717735-3');
</script>

<!-- Article schema for review -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "mainEntityOfPage": {
    "@type": "WebPage",
    "@id": "active-listening"
  },
  "headline": "Active Listening: Tips, Techniques, and Examples",
  "description": "Active listening helps tune out the background noise and tune into your conversations. Here’s how with practical tips, techniques, and examples.",
  "author": {
    "@type": "Person",
    "name": "Darius Contractor"
  },
  "publisher": {
    "@type": "Organization",
    "name": "Otter",
    "logo": {
      "@type": "ImageObject",
      "url": "https://cdn.prod.website-files.com/618e9316785b3582a5178502/65c9f5103ceaab66bd556521_Otter_Blue_Horizontal.png"
    }
  },
  "datePublished": "Jan 28, 2025",
  "dateModified": ""
}
</script>

<!-- Finsweet Attributes -->
<script async type="module"
src="https://cdn.jsdelivr.net/npm/@finsweet/attributes@2/attributes.js"
fs-toc fs-socialshare fs-readtime
></script></head><body class="_2025-background"><div class="page-wrapper"><div class="hide"><div class="google-tag-manager w-embed w-iframe"><!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-M866M5H"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) --></div><div class="css--global w-embed"><style>
  /* --- Basics --- */
  * {
    -webkit-box-sizing: border-box;
    -moz-box-sizing: border-box;
    box-sizing: border-box;
  }
  /* Make the fonts nice! */
  body {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  /* Link's colored from parent */ 
  a {
    color:inherit;
  }

  /* REM Magic */
  :root {
    font-size: 62.5%;
  }

  @media screen and (max-width: 1260px) and (min-width: 1201px) {
    :root {
      font-size: 9.2px;
    }
  }
  @media screen and (max-width: 1200px) and (min-width: 1121px) {
    :root {
      font-size: 8.6px;
    }
  }
  @media screen and (max-width: 1120px) and (min-width: 992px) {
    :root {
      font-size: 7.9px;
    }
  }
  @media screen and (max-width: 991px) {
    :root {
      font-size: 10px;
    }
  }
  @media screen and (max-width: 479px) {
    :root {
      font-size: 10px;
    }
  }

  .w-slider-dot{
    width: 10px;
    height: 8px;
    background: #8294A5;
    opacity: 0.4; 
    transition-property: width;
    transition-duration: 300ms;
    transition-timing-function: cubic-bezier(.455, .03, .515, .955);
  }

  .w-slider-nav.w-round>div {
    border-radius: 8px;
  }

  .w-slider-dot.w-active{
    width: 20px;
    height: 8px;
    background-color: #007AFF;
    opacity: 1;
  }

  .w-nav-overlay,
  .nav-menu{
    top: 0;
    height: auto !important;
  }

  .navbar.floating{
    box-shadow: 0px 1px 1px rgba(0, 0, 0, 0.06), 8px 15px 17px rgba(0, 0, 0, 0.05), 10px 58.5px 41px 16px rgba(24, 57, 89, 0.07);
    position: sticky;
    left: 0%;
    top: 0%;
    right: 0%;
    bottom: auto;
    background-color: white;
  }

  /* --- Inherit links styling --- */
  a {
    color: inherit;
    text-decoration: inherit;
    font-size: inherit;
  }

  .button-gradient:hover .button-gradient-top,
  .footer-logo:hover .footer-logo-embed{
    transform: translate(0.4rem, -0.4rem);
  }
  
  /* A/B Test Buttons Logic */
  [data-primary-buttons]{
  	visibility: hidden;
  }
  [data-button-demo]{
  	display: none;
  }
  
  .wf-design-mode [data-primary-buttons]{
  	visibility: visible;
  }
  .wf-design-mode [data-button-demo]{
  	display: flex !important;
  }
</style></div><div class="rich-text-css w-embed"><style>
.rich-text li:last-child{
	margin-bottom: 0;
}

.rich-text > :first-child{
	margin-top: 0;
}

.blog__note p{
	margin-bottom: 0px;
}

/* Table */
table {
	width: 100%;
  background: white;
  margin-bottom: 4.8rem;
}

table thead th {
		font-size: 1.4rem;
    font-weight: 600;
    text-align: left;
    text-transform: uppercase;
    vertical-align: bottom;
    border-bottom: 2px solid #e7ecf0;
}

th {
		padding: 1.4rem;
    word-wrap: break-word;
		max-width: 22rem;
}

td {
		padding: 1.4rem;
    text-align: left;
    vertical-align: top;
    border-top: 1px solid #e7ecf0;
    font-weight: 400;
    word-wrap: break-word;
		max-width: 22rem;
}
</style></div><div class="css-cf w-embed"><style>
  /* ///////////////////// START OF GLOBAL EDITS ///////////////////// */
  main:focus-visible {
    outline: -webkit-focus-ring-color auto 0px;
  }

  html { font-size: 62.5%; }


  /* --- Font Smoothing --- */
  body {
    -moz-osx-font-smoothing: grayscale;
    -webkit-font-smoothing: antialiased;
  }

  /* Make sure containers never lose their center alignment*/
  .container-medium, .container-small, .container-large {
    margin-right: auto !important;
    margin-left: auto !important;
  }

  /* --- Links --- */
  a:hover [link-arrow]{
    transform: translateX(0.25rem);
  }
  
	a:hover [link-arrow-up-top]{
  	transform: translateX(0.25rem) translateY(-0.25rem);
  }

  [link-arrow],
  [link-arrow-up-top]{
    transition-property: transform;
    transition-duration: 400ms;
    transition-timing-function: cubic-bezier(.215, .61, .355, 1);
  }

  /* --- Rich Text --- */
  /* Get rid of top margin on first element in any rich text element */
  .w-richtext > :not(div):first-child, .w-richtext > div:first-child > :first-child {
    margin-top: 0 !important;
  }

  /* Get rid of bottom margin on last element in any rich text element */
  .w-richtext>:last-child, .w-richtext ol li:last-child, .w-richtext ul li:last-child {
    margin-bottom: 0 !important;
  }
  .text-rich-text li::marker {
    color: black;
  }

  /* --- Inherit links styling --- */
  a {
    color: inherit;
    text-decoration: inherit;
    font-size: inherit;
  }

  /* --- Prevent --- */
  /* Prevent all click and hover interaction with an element */
  .pointer-events-off {
    pointer-events: none;
  }

  /* Enables all click and hover interaction with an element */
  .pointer-events-on {
    pointer-events: auto;
  }

  /*Apply "..." after 3 lines of text */
  .text-style-3lines {
    display: -webkit-box;
    overflow: hidden;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }
  /* Apply "..." after 2 lines of text */
  .text-style-2lines {
    display: -webkit-box;
    overflow: hidden;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  /* Apply "..." at 100% width */
  .truncate-width { 
    width: 100%; 
    white-space: nowrap; 
    overflow: hidden; 
    text-overflow: ellipsis; 
  }

  /* Removes native scrollbar */
  .no-scrollbar {
    -ms-overflow-style: none;  
    overflow: -moz-scrollbars-none;  
  }

  .no-scrollbar::-webkit-scrollbar {
    display: none;
  }

  /* Adds inline flex display */
  .display-inlineflex {
    display: inline-flex;
  }

  /* --- These classes are never overwritten --- */
  .hide {
    display: none !important;
  }

  @media screen and (max-width: 991px), 
    @media screen and (max-width: 767px), 
    @media screen and (max-width: 479px){
      .hide, .hide-tablet{
        display: none !important;
      }
  }

  @media screen and (max-width: 767px){
    .hide-mobile-landscape{
      display: none !important;
    }
  }

  @media screen and (max-width: 479px){
    .hide-mobile{
      display: none !important;
    }
  }
  /* ///////////////////// END OF GLOBAL EDITS ///////////////////// */

  /* ///////////////////// START OF SPACINGS ///////////////////// */
  .margin-0 {
    margin: 0rem !important;
  }

  .padding-0 {
    padding: 0rem !important;
  }

  .spacing-clean {
    padding: 0rem !important;
    margin: 0rem !important;
  }

  .margin-top {
    margin-right: 0rem !important;
    margin-bottom: 0rem !important;
    margin-left: 0rem !important;
  }

  .padding-top {
    padding-right: 0rem !important;
    padding-bottom: 0rem !important;
    padding-left: 0rem !important;
  }

  .margin-right {
    margin-top: 0rem !important;
    margin-bottom: 0rem !important;
    margin-left: 0rem !important;
  }

  .padding-right {
    padding-top: 0rem !important;
    padding-bottom: 0rem !important;
    padding-left: 0rem !important;
  }

  .margin-bottom {
    margin-top: 0rem !important;
    margin-right: 0rem !important;
    margin-left: 0rem !important;
  }

  .padding-bottom {
    padding-top: 0rem !important;
    padding-right: 0rem !important;
    padding-left: 0rem !important;
  }

  .margin-left {
    margin-top: 0rem !important;
    margin-right: 0rem !important;
    margin-bottom: 0rem !important;
  }

  .padding-left {
    padding-top: 0rem !important;
    padding-right: 0rem !important;
    padding-bottom: 0rem !important;
  }

  .margin-horizontal {
    margin-top: 0rem !important;
    margin-bottom: 0rem !important;
  }

  .padding-horizontal {
    padding-top: 0rem !important;
    padding-bottom: 0rem !important;
  }

  .margin-vertical {
    margin-right: 0rem !important;
    margin-left: 0rem !important;
  }

  .padding-vertical {
    padding-right: 0rem !important;
    padding-left: 0rem !important;
  }

  /* ///////////////////// END OF SPACINGS ///////////////////// */

  /* ///////////////////// ELEMENTS ///////////////////// */

  textarea {
    resize: vertical;
  }

  [underline-link]::before,
  [underline-link-alt]::before,
  [underline-link-alt]::after{
    content: "";
    position: absolute;
    bottom: 0em;
    left: 0;
    width: 100%;
    height: 1px;
    background-color: white;
    transition: transform 0.3s cubic-bezier(0.625, 0.05, 0, 1);
    transform-origin: right;
    transform: scaleX(0) rotate(0.001deg);
  }

  [underline-link]:hover::before {
    transform-origin: left;
    transform: scaleX(1) rotate(0.001deg);
  }

  /* Alt */
  [underline-link-alt]::before {
    transform-origin: left;
    transform: scaleX(1) rotate(0.001deg);
    transition-delay: 0.3s;
  }

  [underline-link-alt]:hover::before {
    transform-origin: right;
    transform: scaleX(0) rotate(0.001deg);
    transition-delay: 0s;
  }

  [underline-link-alt]::after {
    transform-origin: right;
    transform: scaleX(0) rotate(0.001deg);
    transition-delay: 0s;
  }

  [underline-link-alt]:hover::after {
    transform-origin: left;
    transform: scaleX(1) rotate(0.001deg);
    transition-delay: 0.3s;
  }

  .button-new.is-link[underline-link]::before,
  .button-new.is-link[underline-link-alt]::before,
  .button-new.is-link[underline-link-alt]::after,
  .text-style-link[underline-link]::before,
  .text-style-link[underline-link-alt]::before,
  .text-style-link[underline-link-alt]::after{
    background-color: #1D25E2;
  }

  .button-new.is-link.is-alternate[underline-link]::before,
  .button-new.is-link.is-alternate[underline-link-alt]::before,
  .button-new.is-link.is-alternate[underline-link-alt]::after{
    background-color: white;
  }


  /* Better Definition – Without Class */
  [underline-link]{
    position: relative;
  }

  [underline-link][underline-link-color="blue"]:hover{
    color: #1D25E2
  }

  [underline-link][underline-link-color="blue"]::before,
  [underline-link-alt][underline-link-color="blue"]::before,
  [underline-link-alt][underline-link-color="blue"]::after{
    background-color: #1D25E2;
  }

  /* Navbar Smaller */
  @media screen and (min-width: 992px){
    .navbar_new .button-new,
    .navbar_new .button-gradient-top{
      font-size: 1.6rem;
      padding: 1.4rem 1.6rem;
    }
    .navbar_new .button-new.is-secondary{
      padding: 1.2rem 1.4rem;
    }
    .navbar_new .button-new.is-link{
      padding: 0rem;
    }
  }

  /* Horizontal Line */
  hr {
    margin-top: 1.2rem;
    margin-bottom: 1.2rem;
    background-color: #E7EAEE;
    border: none;
    height: 1px;
  }
</style></div></div><div class="css--page-specific w-embed"><style>
/* To see widgets in the Designer */
.wf-design-mode .blog_d-widgets{
	display: block;
}

/* Padding on content on Smaller screens */
@media screen and (max-width: 1240px) and (min-width: 992px){
	.blog_d-hero-body{
  	padding: 0 3.2rem;
  }
}

/* Cover Image Hover */
[data-cover-img] {
  transition-property: transform;
  transition-duration: 450ms;
  transition-timing-function: cubic-bezier(0.215, 0.61, 0.355, 1);
  object-fit: cover;
	transform: scale(1);
}

.blog_hero-card_visual:hover [data-cover-img] {
	transform: scale(1.02);
}
</style></div><div class="css--page-specific w-embed"><style>
/*
blockquote::before {
	content: '"'; 
  display: block;
}
*/

.rich-text li:last-child{
	margin-bottom: 0;
}

/*.rich-text > :first-child{
	margin-top: 0;
}*/

.blog__note p{
	margin-bottom: 0px;
}

/* Table */
table {
	width: 100%;
  background: white;
  margin-bottom: 4.8rem;
}

table thead th {
		font-size: 1.6rem;
    font-weight: 600;
    text-align: left;
    text-transform: uppercase;
    vertical-align: bottom;
    border-bottom: 2px solid #e7ecf0;
}

th {
		padding: 1.6rem;
}

td {
		padding: 1.6rem;
    text-align: left;
    vertical-align: top;
    border-top: 1px solid #e7ecf0;
    font-weight: 400;
}

.rich-text-new .button{
  transition-property: color, background-color;
  transition-duration: 350ms, 350ms;
  transition-timing-function: cubic-bezier(.215, .61, .355, 1), cubic-bezier(.455, .03, .515, .955);
	color: white;
  margin-bottom: 3.6rem;
  text-decoration: none;
}
.rich-text-new .button:hover{
	color: white;
}

pre,code{
  display: block;
  font-family: monospace;
  white-space: pre;
  padding: 1.2rem 1.6rem;
  background: #e7ecf0;
  white-space: pre-wrap; 
  word-break: break-word;
}

p code{
  display: inline;
  margin: 1rem 0;
  padding: 0.2rem 0.4rem ;
}

*:focus { outline: none !important;}

html {
    -webkit-tap-highlight-color: transparent;
    -webkit-touch-callout: none;
}

/* Block CTA – Button Hover */
.rich-text-new .blog__cta-block-btn {
  transition-property: color, background-color;
  transition-duration: 350ms, 350ms;
  transition-timing-function: cubic-bezier(.215, .61, .355, 1), cubic-bezier(.455, .03, .515, .955);
  color: #041d34;
}

.rich-text-new .blog__cta-block-v2-btn{
  transition-property: color, background-color;
  transition-duration: 350ms, 350ms;
  transition-timing-function: cubic-bezier(.215, .61, .355, 1), cubic-bezier(.455, .03, .515, .955);
  color: white;
}

.rich-text-new .blog__cta-block-btn:hover,
.rich-text-new .blog__cta-block-v2-btn:hover{
  color: white;
}
</style></div><div class="global-banner"><a href="http://otter.ai/blog/otter-ai-breaks-100m-arr-barrier-and-transforms-business-meetings-launching-industry-first-ai-meeting-agent-suite" class="global-banner_inner w-inline-block"><div class="text-size-small text-weight-medium">Otter.ai breaks $100M ARR barrier and launches industry-first AI Meeting Agent suite.</div><div underline-link-alt="" class="button-new is-link is-alternate"><div>Learn more</div></div></a><div class="css-component w-embed"><style>
.global-banner .button-new{
  flex-grow: 0;
  flex-shrink: 0;
  flex-basis: auto;
  width: auto !important; 
}
</style></div></div><header class="nav_wrapper"><div data-animation="default" class="navbar_new w-nav" data-easing2="ease" data-easing="ease" data-collapse="medium" data-w-id="c3a3356b-e675-e05c-327b-3566f7022f9b" role="banner" data-no-scroll="1" data-duration="0" id="navbar"><div class="nav-wrap_new"><a href="/meeting-agent" class="brand_new w-nav-brand"><div class="nav_logo w-embed"><svg width="100%" height="100%" viewBox="0 0 57 22" fill="none" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M36.1707 0.304565C34.6356 0.304565 33.3867 1.55337 33.3867 3.08845V18.7112C33.3867 20.2463 34.6356 21.4951 36.1707 21.4951C37.7058 21.4951 38.9546 20.2463 38.9546 18.7112V3.08845C38.9546 1.55337 37.7058 0.304565 36.1707 0.304565Z" fill="currentColor"></path>
<path fill-rule="evenodd" clip-rule="evenodd" d="M30.3725 3.08857C30.3725 1.55349 29.1237 0.304688 27.5886 0.304688C26.0535 0.304688 24.8047 1.55349 24.8047 3.08857V18.7113C24.8047 20.2464 26.0535 21.4952 27.5886 21.4952C29.1237 21.4952 30.3725 20.2464 30.3725 18.7113V3.08857Z" fill="currentColor"></path>
<path fill-rule="evenodd" clip-rule="evenodd" d="M44.7468 7.35156C43.2117 7.35156 41.9629 8.60037 41.9629 10.1354V11.9747C41.9629 13.5098 43.2117 14.7586 44.7468 14.7586C46.2819 14.7586 47.5307 13.5098 47.5307 11.9747V10.1354C47.5307 8.60037 46.2819 7.35156 44.7468 7.35156Z" fill="currentColor"></path>
<path fill-rule="evenodd" clip-rule="evenodd" d="M53.323 4.28906C51.7879 4.28906 50.5391 5.53787 50.5391 7.07295V14.7305C50.5391 16.2655 51.7879 17.5144 53.323 17.5144C54.8581 17.5144 56.1069 16.2655 56.1069 14.7305V7.07295C56.1069 5.53787 54.8581 4.28906 53.323 4.28906Z" fill="currentColor"></path>
<path d="M10.8996 0C4.88799 0 0 4.8915 0 10.8994C0 16.9073 4.89156 21.7989 10.8996 21.7989C16.9075 21.7989 21.7991 16.9073 21.7991 10.8994C21.7991 4.8915 16.9075 0 10.8996 0ZM10.9103 16.4887C7.78999 16.4887 5.24938 13.9481 5.24938 10.8279C5.24938 7.7076 7.78999 5.16702 10.9103 5.16702C14.0306 5.16702 16.5712 7.7076 16.5712 10.8279C16.5712 13.9481 14.0306 16.4887 10.9103 16.4887Z" fill="currentColor"></path>
</svg></div></a><nav role="navigation" class="nav-menu w-nav-menu"><div class="w-layout-grid nav-items-new"><div data-delay="150" data-hover="true" class="nav__dropdown-new w-dropdown"><div class="nav__dropdown-toggle-new w-dropdown-toggle"><div class="dropdown-nav-label-new">Agents</div><div class="nav__dropdown-arrow-new w-embed"><svg width="8" height="6" viewBox="0 0 8 6" fill="none" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M0.587756 1.28474C0.67482 1.07455 0.879928 0.9375 1.10744 0.9375H7.10744C7.33495 0.9375 7.54006 1.07455 7.62712 1.28474C7.71418 1.49493 7.66606 1.73687 7.50519 1.89775L4.50519 4.89775C4.28552 5.11742 3.92936 5.11742 3.70969 4.89775L0.709691 1.89775C0.548817 1.73687 0.500692 1.49493 0.587756 1.28474Z" fill="currentColor"/>
</svg></div></div><nav class="nav__dropdown-list-new w-dropdown-list"><div class="nav__dropdown-box"><div class="nav__dropdown-inner-new_left"><div class="nav__dropdown-list-new-title"><div class="text-color-black"><div class="text-size-large">Something for everyone</div></div></div><div class="nav__dropdown-inner-new"><a href="/sales-agent" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_circle"><img loading="lazy" src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67dc3a840a0a1f98ac461772_dropdown_circle1.png" alt="" class="img-cover"/></div><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Sales Agent</div></div></div><div class="opacity-70"><div class="text-color-black"><p class="text-size-tiny">Automate follow-ups, capture notes, sync with CRM.</p></div></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="/recruiting-agent" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_circle"><img loading="lazy" src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67dc3a840a0a1f98ac461776_dropdown_circle4.png" alt="" class="img-cover"/></div><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Recruiting Agent</div></div></div><div class="opacity-70"><div class="text-color-black"><p class="text-size-tiny">Get insights, draft follow-ups, sync notes.</p></div></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="/education-agent" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_circle"><img loading="lazy" src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67dc3a840a0a1f98ac461778_dropdown_circle2.png" alt="" class="img-cover"/></div><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Education Agent</div></div></div><div class="opacity-70"><div class="text-color-black"><p class="text-size-tiny">Organize notes, extract insights, and structure ideas.</p></div></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="/media-agent" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_circle"><img loading="lazy" src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67dc3a840a0a1f98ac461774_dropdown_circle3.png" alt="" class="img-cover"/></div><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Media Agent</div></div></div><div class="opacity-70"><div class="text-color-black"><p class="text-size-tiny">Streamline insights, structure content, collaborate.</p></div></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a></div></div></div></nav></div><a href="/pricing/meeting-agent" data-tracking-type="button" class="nav-link-new w-nav-link">Pricing</a><div data-delay="150" data-hover="true" class="nav__dropdown-new w-dropdown"><div class="nav__dropdown-toggle-new w-dropdown-toggle"><div class="dropdown-nav-label-new">Resources</div><div class="nav__dropdown-arrow-new w-embed"><svg width="8" height="6" viewBox="0 0 8 6" fill="none" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M0.587756 1.28474C0.67482 1.07455 0.879928 0.9375 1.10744 0.9375H7.10744C7.33495 0.9375 7.54006 1.07455 7.62712 1.28474C7.71418 1.49493 7.66606 1.73687 7.50519 1.89775L4.50519 4.89775C4.28552 5.11742 3.92936 5.11742 3.70969 4.89775L0.709691 1.89775C0.548817 1.73687 0.500692 1.49493 0.587756 1.28474Z" fill="currentColor"/>
</svg></div></div><nav class="nav__dropdown-list-new is-resources w-dropdown-list"><div class="nav__dropdown-box is-resources"><div class="nav__dropdown-inner-new_box"><div class="nav__dropdown-inner-new_left"><div class="nav__dropdown-list-new-title"><div class="text-color-black"><div class="text-size-large">Learn, explore, level up</div></div></div><div class="nav__dropdown-inner-new is-resources"><a href="https://help.otter.ai/hc/en-us?_gl=1*3ab6if*_gcl_au*NjMyOTM1Mzk0LjE3Mzg1Mzg4MTA.*_ga*NTEyNTUzNzIuMTY3NTUzODMyNg..*_ga_F0G9HT49XE*MTc0MjQ5NDQ3My4xMzI4LjEuMTc0MjUxOTAzNi41Mi4wLjY4NzE1NDU1Mw..*_fplc*SkJuaFFIN0dXcWtDa041bnBIdDI4dWUzQWppRjM0V1AzJTJCR3A1bnJ4enh6N1NYTzNaSDRzQ0FIcXRaS3JtMWlMZGpVTjRzJTJCdUFHbFMlMkY0czdtY3EzMDE2RG9pWWFSeUc4VlNTWEVlREU3ZlR4U2xxJTJGak1JZk0wQTVnbVAwZ1ElM0QlM0Q.*_ga_718GRVQGD7*MTc0MjQ5NDQ3My4yMjEuMS4xNzQyNTE5MDI5LjYwLjAuNjE3MzkwNjkz" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Help Center</div></div></div><div class="text-color-black"><p class="text-size-tiny">Find FAQs, troubleshooting tips, and setup guides.</p></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="/2025/careers" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Careers</div></div></div><div class="text-color-black"><p class="text-size-tiny">Join our team to shape the future of AI productivity.</p></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="#" class="nav__dropdown-link-new hide w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Getting Started</div></div></div><div class="text-color-black"><p class="text-size-tiny">Tutorials to help you get up and running fast.</p></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="/2025/press" class="nav__dropdown-link-new w-inline-block"><div class="nav__dropdown-link-new_inner"><div class="nav__dropdown-link-new_text-wrap"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Press</div></div></div><div class="text-color-black"><p class="text-size-tiny">Discover the latest product and company news.</p></div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a></div></div><div class="nav__dropdown-inner-new_right"><div class="text-color-black"><div class="text-size-large">The Conversation</div></div><a href="/blog" class="nav__dropdown-inner-new_visual w-inline-block"><img loading="lazy" src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67dc3b85ee0d2ba08c8a7423_dropdown_img.avif" alt="" class="img-cover"/></a><div class="nav__dropdown-inner-new_right-bottom"><div class="text-weight-normal"><p class="text-size-small">Get the latest on how to use Otter.ai to boost your productivity.</p></div><a href="/2025/blog" underline-link-alt="" class="button-new is-link w-inline-block"><div>View our blog</div><div class="nav__dropdown-link_icon is-link w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a></div></div></div></div></nav></div><div data-delay="150" data-hover="true" class="nav__dropdown-new w-dropdown"><div class="nav__dropdown-toggle-new w-dropdown-toggle"><div class="dropdown-nav-label-new">Download</div><div class="nav__dropdown-arrow-new w-embed"><svg width="8" height="6" viewBox="0 0 8 6" fill="none" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M0.587756 1.28474C0.67482 1.07455 0.879928 0.9375 1.10744 0.9375H7.10744C7.33495 0.9375 7.54006 1.07455 7.62712 1.28474C7.71418 1.49493 7.66606 1.73687 7.50519 1.89775L4.50519 4.89775C4.28552 5.11742 3.92936 5.11742 3.70969 4.89775L0.709691 1.89775C0.548817 1.73687 0.500692 1.49493 0.587756 1.28474Z" fill="currentColor"/>
</svg></div></div><nav class="nav__dropdown-list-new is-download w-dropdown-list"><div class="nav__dropdown-box"><div class="nav__dropdown-inner-new_left"><div class="nav__dropdown-list-new-title"><div class="text-color-black"><div class="text-size-large">Stay connected across devices</div></div></div><div class="nav__dropdown-inner-new"><a href="https://apps.apple.com/us/app/otter-voice-meeting-notes/id1276437113" class="nav__dropdown-link-new w-inline-block"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">iOS App</div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="https://play.google.com/store/apps/details?id=com.aisense.otter" class="nav__dropdown-link-new w-inline-block"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Android App</div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a><a href="https://chrome.google.com/webstore/detail/otterai-transcribe-record/bnmojkbbkkonlmlfgejehefjldooiedp" class="nav__dropdown-link-new w-inline-block"><div class="text-color-blue"><div class="text-weight-bold"><div class="text-size-small">Chrome Extension</div></div></div><div class="nav__dropdown-link_icon w-embed"><svg width="100%" height="100%" viewBox="0 0 5 8" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 4L1 7L1 1L4 4Z" fill="currentColor" stroke="currentColor" stroke-width="1.125" stroke-linejoin="round"></path>
</svg></div></a></div></div></div></nav></div></div><div class="w-layout-grid nav-items-new"><a id="schedule-demo-btn" data-tracking-type="button" href="/2025/demo" class="nav-link-new is-schedule w-node-c3a3356b-e675-e05c-327b-3566f702304f-f7022f9b w-inline-block"><div id="demo-action-btn">Schedule demo</div></a><a id="demo-btn" data-tracking-type="button" data-button="demo-btn" href="https://javascript:void(0)" class="nav-link-new is-demo w-node-c3a3356b-e675-e05c-327b-3566f7023052-f7022f9b w-inline-block"><div id="demo-action-btn">Try Demo</div></a><a id="demo-nav-link" data-tracking-type="button" href="/signin" class="nav-link-new is-schedule w-node-_519cb0bc-f8d9-28b7-9e52-612fa1fce7db-f7022f9b w-inline-block"><div id="demo-action-btn">Log in</div></a><div class="nav-divider"></div><div id="w-node-c3a3356b-e675-e05c-327b-3566f7023055-f7022f9b" class="nav-button-group"><a data-tracking-type="button" href="/startforfree/meeting-agent" class="button-gradient w-inline-block"><div class="button-gradient-top is-blue"><div>Start for free</div></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67d0367d5ad3fbc59c5ecdf3_hot-gradient.jpg" loading="lazy" alt="" class="button-gradient-bottom"/></a></div></div></nav><div class="menu-button w-nav-button"><div class="nav__menu-icon-wrap"><div class="nav__menu-icon-label-wrap"><div class="nav__menu-label menu">Menu</div><div class="nav__menu-label close">Close</div></div><div class="nav__menu-icon"><div class="nav__menu-top-line"></div><div class="nav__menu-bottom-line"></div></div></div></div></div></div></header><section class="section_blog-d-hero"><div class="padding-global"><div class="container-large"><div class="blog_d-hero-container"><div class="blog_d-hero-tag-wrap"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-regular">Productivity Hacks</div></a><a href="/2025/press" class="blog_d-hero-tag w-inline-block w-condition-invisible"><div class="text-size-regular">Productivity Hacks</div></a></div><div class="blog_d-hero-head"><div class="blog_d-hero-head_inner"><div class="text-color-blue"><h1 class="heading-style-h1">Active Listening: Tips, Techniques, and Examples</h1></div><div class="blog_d-hero-head_author-wrap"><a href="/author/darius-contractor" class="w-inline-block"><div class="blog_d-hero-head_author-wrap_top"><div class="blog_d-hero-head_author-photo"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/66c6127ede859392e4275446_T2VL9UPGT-U03KTJD2AQ1-b12219b68347-192.png" loading="lazy" alt="" class="img-cover"/></div><div class="text-color-content-default"><div class="text-weight-medium"><div class="text-size-large">Darius Contractor</div></div></div></div></a><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">January 28, 2025</div><div class="blog_d-hero-head_author-dot"></div><div class="blog_d-hero-head_author-read"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="text-size-medium"><span fs-readtime-element="time">7</span> min</div></div></div></div></div><div class="blog_d-hero-head_visual"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/68627641052699af345971c4_685dc6d2b61ade1efd9b3a0c_679928c91e9ce2c26871220a_active-Listening.jpeg" loading="lazy" alt=""/></div></div><div class="blog_d-hero-container_inner"><div class="blog_d-hero-content-box"><div class="blog_d-hero-content_top w-condition-invisible"><div class="text-weight-medium"><div class="text-size-large">In this article</div></div><div><div><a href="#" class="blog_d-hero-content_link w-inline-block"><div fs-toc-element="link" class="text-size-medium">Heading 2</div></a></div></div></div><div class="hide-tablet"><div class="blog_d-hero-content_cta"><div class="blog_d-hero-content_cta-top"><div class="heading-style-h4">Try Otter today</div><ul role="list" class="blog_d-hero-content_cta-list"><li class="blog_d-hero-content_cta-item"><div class="text-weight-medium"><p class="text-size-medium">300 monthly transcription minutes</p></div></li><li class="blog_d-hero-content_cta-item"><div class="text-weight-medium"><p class="text-size-medium">30 minutes per conversation</p></div></li><li class="blog_d-hero-content_cta-item"><div class="text-weight-medium"><p class="text-size-medium">3 audio or video file imports</p></div></li></ul></div><div class="blog_d-hero-content_buttton-wrap"><a data-tracking-type="button" href="/startforfree/meeting-agent" class="button-gradient w-inline-block"><div class="button-gradient-top is-blue"><div>Start for free</div></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67d0367d5ad3fbc59c5ecdf3_hot-gradient.jpg" loading="lazy" alt="" class="button-gradient-bottom"/></a></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg.avif" loading="lazy" sizes="(max-width: 2622px) 100vw, 2622px" srcset="https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg-p-500.png 500w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg-p-800.png 800w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg-p-1080.png 1080w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg-p-1600.png 1600w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg-p-2000.png 2000w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551d5ce36dcbcc46fdc171_blog_cta-bg.avif 2622w" alt="" class="blog_d-hero-content_cta-bg"/><div class="noise is-cta"></div></div></div><div class="blog_d-hero-content_bottom"><div class="text-weight-medium"><div class="text-size-large">Share this post</div></div><div class="blog_d-hero-content_bottom-social-list"><a fs-socialshare-element="linkedin" href="#" class="blog_d-hero-content_bottom-social-link w-inline-block"><div class="blog_d-hero-content_bottom-social-icon w-embed"><svg width="100%" height="100%" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
<g clip-path="url(#clip0_13532_83163)">
<path d="M23.9394 2.33398H4.05597C3.1035 2.33398 2.33331 3.08594 2.33331 4.01563V23.9811C2.33331 24.9108 3.1035 25.6673 4.05597 25.6673H23.9394C24.8919 25.6673 25.6666 24.9108 25.6666 23.9857V4.01563C25.6666 3.08594 24.8919 2.33398 23.9394 2.33398ZM9.25584 22.2174H5.7923V11.0794H9.25584V22.2174ZM7.52407 9.56185C6.41209 9.56185 5.5143 8.66406 5.5143 7.55664C5.5143 6.44922 6.41209 5.55143 7.52407 5.55143C8.63149 5.55143 9.52928 6.44922 9.52928 7.55664C9.52928 8.65951 8.63149 9.56185 7.52407 9.56185ZM22.2168 22.2174H18.7578V16.8034C18.7578 15.5137 18.735 13.8503 16.9577 13.8503C15.1575 13.8503 14.8841 15.2585 14.8841 16.7122V22.2174H11.4297V11.0794H14.7474V12.6016H14.7929C15.2532 11.7266 16.3834 10.8014 18.0651 10.8014C21.5696 10.8014 22.2168 13.1074 22.2168 16.1061V22.2174Z" fill="currentColor"></path>
</g>
<defs>
<clipPath id="clip0_13532_83163">
<rect width="23.3333" height="23.3333" fill="currentColor" transform="translate(2.33331 2.33398)"></rect>
</clipPath>
</defs>
</svg></div></a><a fs-socialshare-element="x" href="#" class="blog_d-hero-content_bottom-social-link w-inline-block"><div class="blog_d-hero-content_bottom-social-icon w-embed"><svg width="100%" height="100%" viewBox="0 0 29 28" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M20.8169 4.18359H24.0966L16.9313 12.3731L25.3608 23.5172H18.7606L13.5911 16.7584L7.67598 23.5172H4.39423L12.0583 14.7576L3.97186 4.18359H10.7396L15.4124 10.3614L20.8169 4.18359ZM19.6658 21.5541H21.4831L9.75211 6.04358H7.80189L19.6658 21.5541Z" fill="currentColor"></path>
</svg></div></a><a fs-socialshare-element="facebook" href="#" class="blog_d-hero-content_bottom-social-link w-inline-block"><div class="blog_d-hero-content_bottom-social-icon w-embed"><svg width="100%" height="100%" viewBox="0 0 29 28" fill="none" xmlns="http://www.w3.org/2000/svg">
<g clip-path="url(#clip0_13532_83167)">
<path d="M14.3333 2.33398C7.89003 2.33398 2.66663 7.55738 2.66663 14.0007C2.66663 19.4719 6.43356 24.0629 11.5151 25.3239V17.566H9.10943V14.0007H11.5151V12.4644C11.5151 8.49352 13.3122 6.65298 17.2108 6.65298C17.95 6.65298 19.2254 6.79812 19.7471 6.94278V10.1745C19.4718 10.1455 18.9934 10.1311 18.3994 10.1311C16.4865 10.1311 15.7473 10.8558 15.7473 12.7397V14.0007H19.5581L18.9034 17.566H15.7473V25.5819C21.5242 24.8843 26.0004 19.9656 26.0004 14.0007C26 7.55738 20.7766 2.33398 14.3333 2.33398Z" fill="currentColor"></path>
</g>
<defs>
<clipPath id="clip0_13532_83167">
<rect width="23.3333" height="23.3333" fill="currentColor" transform="translate(2.66663 2.33398)"></rect>
</clipPath>
</defs>
</svg></div></a><div fs-socialshare-element="x-username" class="hide">otter_ai</div></div></div></div><div class="blog_d-hero-body"><div class="blog-update_box is-2025 w-condition-invisible"><div class="blog-update_box-content"><div class="blog-update_label">Update</div><div><div class="margin-bottom margin-12"><div class="heading-style-h4">Otter has transformed with Otter Meeting Agents</div></div><p class="text-size-medium">Intelligent, voice-activated, meeting agents that directly participate in meetings answering questions and completing tasks - to make capturing, understanding, and acting on conversations effortless. Learn more about what’s new here.</p></div><a href="/meeting-agent" class="button-gradient w-inline-block"><div class="button-gradient-top is-alternate"><div>Learn more</div></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67d0367d5ad3fbc59c5ecdf3_hot-gradient.jpg" loading="lazy" alt="" class="button-gradient-bottom"/></a></div></div><div fs-toc-hideurlhash="true" fs-toc-element="contents" fs-readtime-element="contents" fs-toc-offsettop="10rem" class="rich-text-new w-richtext"><p>“What did you say?” </p><p>With so many potential distractions — a loud office, constant notifications, and a crowded to-do list — it’s no wonder our attention sometimes slips. But tuning it all out to pay attention to conversations is an indispensable skill. </p><p>Active listening is more than just hearing words. It’s about understanding, retaining, and engaging in conversations. </p><p>Let’s explore how to sharpen your active listening skills to boost productivity and communication. Discover practical techniques, examples of active listening in action, and the benefits of truly hearing what others have to say. </p><h2>What’s active listening? </h2><p>Active listening is the practice of fully engaging in a conversation. When you actively listen, you enhance your ability to understand the message and respond thoughtfully. You can use several techniques, including making direct eye contact, asking open-ended questions, and paying attention to non-verbal cues like body language and facial expressions. </p><p>Whether engaging with a client or <a href="https://otter.ai/blog/ways-to-improve-your-interviewing-skills?0db891cc_page=7&amp;28959088_page=3&amp;7bd4a6f3_page=3&amp;84d5663d_page=2">leading a job interview</a>, active listening improves overall communication and builds trust. It’s a skill that doesn’t just foster strong relationships. It leads to better collaboration, a stronger sense of connection, and more productive work. </p><p>Good listeners abide by the three As: </p><ul role="list"><li><strong>Attitude: </strong>A curious and open mindset anchors the conversation. Positive attitudes signal respect and make the speaker feel comfortable. </li><li><strong>Attention: </strong>Small gestures like nodding your head or asking clarifying questions show active engagement. Staying present means demonstrating your undivided focus on the speaker. </li><li><strong>Adjustment: </strong>Sometimes, someone needs to vent. Other times, they might need a partner to work out an idea. Effective listening requires flexibility. Being attentive to someone&#x27;s needs demonstrates empathy and leads to more meaningful dialogues. </li></ul><h2>6 active listening strategies for better conversations</h2><p>Good listeners sharpen their techniques with a wide set of communication skills. Each one helps you connect with others, hear the other person, and respond empathetically. </p><p>Here are six active listening techniques to bring to the table: </p><h3>1. Stay focused</h3><p>There’s no shortage of excuses for getting distracted, whether it’s the ping of a new notification or an email you forgot to respond to. Tuning out the noise is crucial to active listening. Tools like <a href="https://get.otter.ai/">Otter’s AI meeting assistant</a> help you resist the urge to multitask by taking notes for you, allowing you to be present in the moment without losing track of important details. </p><h3>2. Summarize key points</h3><p>Throughout the conversation, paraphrase and summarize what’s being said. Paraphrasing key points helps you check that everyone is on the same page and prevent misunderstandings. This reinforces your own understanding and shows the speaker you value their input. </p><h3>3. Don’t interrupt</h3><p>It’s tempting to jump in with your thoughts, but interruptions can derail the conversation. Let the other person finish their point. Sometimes, the best conversation comes when you give someone room to express themselves fully. By waiting until they finish, you show respect and encourage team members to speak openly. </p><h3>4. Ask open-ended questions</h3><p>Yes/no questions are a quick way to cut a conversation short. Ask questions that help you learn more about the topic, like, “How does this make you feel?” or “What’s the best-case scenario to improve this situation?” to encourage deeper thinking and show your interest in the speaker’s opinion. </p><h3>5. Read the room</h3><p>Active listeners don’t just listen to words. They pay careful attention to nonverbal cues like body language, facial expressions, and tone. If someone’s posture is tense and they speak with a shaky voice, these cues might indicate they feel uneasy — even if their words paint a different picture. </p><h3>6. Set judgments aside</h3><p>Active listening is about understanding the content and emotions behind someone’s words. Set aside any judgments or preconceived notions and focus on understanding the speaker’s perspective. When you show empathy, you nurture an environment where people feel heard and empowered to share their emotions openly. </p><h2>Benefits of active listening </h2><p>Learning how to be an active listener takes time, patience, and trial and error. And like any other new skill, the benefits make the effort worthwhile:</p><ul role="list"><li><strong>Dig beyond the surface: </strong>Active listeners go beyond superficial conversations and build real, meaningful connections. These connections construct a sense of place, community, and belonging — all of which are powerful motivators. When people feel understood, they create a workplace environment where collaboration and trust thrive. </li><li><strong>Strengthen collaboration:</strong> Active listening techniques mitigate misunderstandings, which are often at the heart of workplace communication breakdowns. When you listen carefully, paraphrase, and clarify conversation points, you make sure everyone is on the same page about expectations and goals. This shared understanding lets teams work more cohesively, making collaboration smooth and effective. </li><li><strong>Help resolve conflicts:</strong> Remember those strong interpersonal connections you built through active listening? Conflict resolution is where they come into play. By practicing active listening, you’re more likely to see things from the other person’s perspective, allowing empathy to lead you through disagreements. And when people feel understood and respected, they’re more likely to seek common ground. </li><li><strong>Boost engagement and team morale:</strong> Connection and respect are like rocket fuel for motivation. Active listening builds a positive culture where everyone feels like their voice matters, boosting morale and engagement. People are more excited to contribute their ideas when they know the person on the other end of the conversation truly listens.</li><li><strong>Promote continuous growth: </strong>Every conversation is an opportunity to learn something new. Active listening opens you up to different perspectives and insights, which can expand your own understanding. As you actively listen, you learn from others and, in turn, help them learn too. </li></ul><h2>3 examples of effective active listening</h2><p>What does active listening look like in the wild? Here are three scenarios:</p><h3>1. During a team meeting</h3><p>Your team gets together to deliver a status update on an ongoing project. Everyone silences their phone and closes their laptops. You all ask thoughtful questions and give each other the space to respond, leading to a more productive meeting. </p><h3>2. During a client call</h3><p>Before the call begins, you set the stage for a focused conversation. You close unnecessary tabs, silence your phone, and blur your background. As the client shares their concerns, you nod and avoid interrupting to indicate your commitment to the conversation. </p><h3>3. During a job interview</h3><p>Create a calm, distraction-free environment for both parties. As the candidate speaks, you <a href="https://otter.ai/blog/your-full-guide-to-note-taking-methods-tools?0db891cc_page=25&amp;28959088_page=2&amp;6bb1b90d_page=2&amp;84d5663d_page=5">take interview notes</a> without breaking eye contact, point your body toward them, and ask thoughtful questions to dig deeper into their experience. </p><h2>How to improve your active listening skills: 5 tips</h2><p>Not sure where to start training your active listening skills? Listen up. Here are five tips: </p><ol role="list"><li><strong>Ask for feedback: </strong>After a conversation, ask a trusted colleague how you did as a listener. Did you make them feel heard? Their feedback might uncover listening skills that need improvement, even if you felt fully engaged. </li><li><strong>Check-in with yourself: </strong>It’s easy to zone out during long meetings. Pay attention to when your mind wanders. A quick mental reminder to refocus can make a big difference in staying present. </li><li><strong>Be open: </strong>Listen to the other person’s perspective without rushing to respond, even if you disagree. You might learn something new and build mutual respect in the process. </li><li><strong>Take small breaks: </strong>Long conversations can drain anyone. Don’t be afraid to ask for a mental breather to recharge. Say something like, “Do you mind if I had a moment to think about this?” This establishes a mutually beneficial exchange and helps you stay sharp and engaged. </li><li><strong>Let silence in: </strong>Sometimes, the best thing you can do is be quiet. Let a pause linger. It will give you and the speaker space to process and respond thoughtfully rather than fill the gaps. </li></ol><p>Remember, striving to be a good listener isn’t about striving for perfection. It’s about building better habits to stay connected in your conversations. Give yourself space and grace to learn. </p><h2>Great listeners need great notes with Otter </h2><p>Good conversations call for <a href="https://otter.ai/blog/your-full-guide-to-note-taking-methods-tools?0db891cc_page=25&amp;28959088_page=2&amp;6bb1b90d_page=2&amp;84d5663d_page=5">detailed note-taking</a>. With Otter, you never get distracted jotting down insights and next steps. </p><p>Otter is revolutionizing AI at work as the first AI meeting assistant that auto joins, auto shares, and auto summarizes meetings. AI-powered meeting assistants are becoming standard in most enterprise settings,<a href="https://otter.ai/how-otter-ai-can-save-you-time-at-work"> saving professionals and teams an average of 4 hours a week</a> and increasing productivity by automatically generating action items, summaries, and follow-up emails. Try Otter now and see the difference smart technology can make.<a href="https://otter.ai/demo"> Get started today. </a></p></div><div class="blog_d-widgets"><div class="blog_d-hero-content_cta is-big"><div class="blog_d-hero-content_cta-top is-big"><div class="heading-style-h4">Try Otter today</div><ul role="list" class="blog_d-hero-content_cta-list"><li class="blog_d-hero-content_cta-item"><div class="text-weight-medium"><p class="text-size-medium">300 monthly transcription minutes</p></div></li><li class="blog_d-hero-content_cta-item"><div class="text-weight-medium"><p class="text-size-medium">30 minutes per conversation</p></div></li><li class="blog_d-hero-content_cta-item"><div class="text-weight-medium"><p class="text-size-medium">3 audio or video file imports</p></div></li></ul></div><div class="blog_d-hero-content_cta-button-wrap"><a data-tracking-type="button" href="/startforfree/meeting-agent" class="button-gradient w-inline-block"><div class="button-gradient-top is-blue"><div>Start for free</div></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67d0367d5ad3fbc59c5ecdf3_hot-gradient.jpg" loading="lazy" alt="" class="button-gradient-bottom"/></a></div><div class="noise is-cta"></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big.avif" loading="lazy" sizes="(max-width: 2997px) 100vw, 2997px" srcset="https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big-p-500.png 500w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big-p-800.png 800w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big-p-1080.png 1080w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big-p-1600.png 1600w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big-p-2000.png 2000w, https://cdn.prod.website-files.com/618e9316785b3582a5178502/68551f38b46380dc251ca5e7_blog_cta-bg-big.avif 2997w" alt="" class="blog_d-hero-content_cta-bg is-big"/></div></div></div></div></div></div></div></section><section class="section_blog-d-related"><div class="padding-global"><div class="container-large"><div class="blog_d-related_container"><div class="text-color-blue"><h2 class="heading-style-h2">Related posts</h2></div><div><div class="blog_d-related-collection-wrap w-dyn-list"><div role="list" class="blog_d-related-collection-list w-dyn-items"><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/client-communication" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/6862764c49f844f67366b6ce_685dc6e1af75d75af5ba4151_67d9d354ceee9be466653fec_Client%252520Communication.jpeg" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/client-communication" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">How To Improve Client Communication: 10 Best Practices</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Clear communication is key to successful meetings. Discover tips for improving client communication and building stronger relationships with Otter.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/sales-pitch" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71533b1dc525828d80d_67007572dcd42bb18b13505e_sales-pitch.jpeg 4000w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/sales" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Sales</div></a><a href="/2025/2025-blog/sales-pitch" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">Sales Pitch Strategies and Examples: How To Win Over Your Audience</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Writing the best sales pitch lets you captivate the audience and convert leads, boosting your sales. Find out how with these strategies and examples.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Max Garber</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/virtual-meeting-etiquette-guide" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6dee70fdb96bc2f388e_6720bcc4632623f9029b13de_speech-to-text.jpeg 4000w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/virtual-meeting-etiquette-guide" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">13 Virtual Meeting Etiquette Rules and 9 Mistakes To Avoid</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Master virtual meeting etiquette with these tips for keeping your meetings professional and productive.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/good-interview-notes" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/6862765b643807b2a4693f1d_685dc6ee92dfefe93cc2b46e_6720e94e1cd203b14c045522_%252520Interview-Notes.jpeg" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/good-interview-notes" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">How To Take Interview Notes Like a Pro: 10 Tips</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Taking great interview notes makes following up easier, from action items to next steps. Here are 10 tips to improve your notetaking strategies.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/ways-to-improve-your-interviewing-skills" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc6e08cf2be2681b8e112_67992a49c13351c3301a64b2_Check%2520in%2520Meeting.jpeg 4000w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/ways-to-improve-your-interviewing-skills" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">Top 12 Interviewing Skills Every Professional Needs to Know</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Recruiting a new hire? Learn which interviewing skills you need to scope out top talent, and discover how Otter makes hiring a breeze.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Darius Contractor</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/how-to-type-faster" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/68627666cbe52a950eb9fd3c_685dc6f76d30dfdaa383f5f3_67aba8478b09ab858c312ae6_how-to-type-faster.jpeg" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/how-to-type-faster" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">How To Type Faster: 12 Tips for Improving Speed</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Discover how to type faster with 12 practical tips to rev up your speed, boost your productivity, and leave two-fingered typing in the dust.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/your-full-guide-to-note-taking-methods-tools" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc72a060a6dda6cf7c452_673e267b82cc978eef4032e5_note-taking-methods.jpeg 4000w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/your-full-guide-to-note-taking-methods-tools" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">The 6 Best Note-Taking Methods: A Guide</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">Ready to master the art of good note-taking? Here are six effective note-taking methods to add to your toolkit, along with tips for better notes.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Darius Contractor</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/out-of-office-message" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc712c73fd5c896266f5a_67b4cc86f82816850fb77293_Out%2520of%2520Office.jpeg 4000w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/out-of-office-message" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">How To Write an Out-of-Office Message: 10 Examples</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">An out-of-office message keeps everything running smoothly while you’re away. Here are some tips and tricks to draft the perfect email.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Darius Contractor</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/best-follow-up-emails" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/68627649b55301dafea21369_685dc6dc5f79231dbf9a1909_6710c59f0fe957937482f8d6_%252520Best-Follow-Up-Emails.jpeg" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="/2025/2025-tag/productivity-hacks" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="/2025/2025-blog/best-follow-up-emails" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p data-maxchars-heading="73" class="text-size-medium">How To Write the Best Follow-Up Emails: Templates and Best Practices</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p data-maxchars-subheading="80" class="text-size-medium">When it comes to writing emails, every word counts. Here are five of the best follow-up email templates to get people to hit “reply.”</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div></div></div></div><div class="w-condition-invisible"><div class="blog_d-related-collection-wrap w-dyn-list"><div role="list" class="blog_d-related-collection-list w-dyn-items"><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/bonjour-hola-otter-ai-expands-ai-meeting-assistant-to-support-french-and-spanish" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/6862764b65277a55543bdc5b_685dc6df572c220acb7e3f5a_6718eee4d934f2d4d0146fca_French.png" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="#" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Press Releases</div></a><a href="#" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p class="text-size-medium">Bonjour! ¡Hola! Otter.ai Expands AI Meeting Assistant to Support French and Spanish</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p class="text-size-medium">Otter.ai, the leading AI meeting assistant, today announced the addition of real-time French and Spanish transcription, marking a milestone as Otter continues to break down communication barriers and provide a more collaborative experience for teams worldwide</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Otter</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/the-future-of-sales-how-ai-is-transforming-the-game-in-2024" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71e861c3663bf26d1cf_659dad8512698e26cec58930_pexels-linkedin-sales-navigator-7245802.jpeg 7952w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="#" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Sales</div></a><a href="#" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p class="text-size-medium">The Future of Sales: How AI is Transforming the Game in 2024</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p class="text-size-medium">The world of sales is constantly evolving, and 2024 is shaping up to be a landmark year thanks to the ever-increasing influence of artificial intelligence. From prospecting and lead generation to personalization and closing deals, AI is poised to reshape the sales landscape in ways we can only begin to imagine.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Dustin Crawford</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/otterpilot-vs-zoom-ai-companion-which-ai-meeting-assistant-is-better-for-your-meetings" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/6862767e177c485793f8b6d2_685dc71255f528fbbfca53d9_651da68ac62b3f0caab0c35a_Banner%2525202_B.png" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="#" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="#" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p class="text-size-medium">Otter vs Zoom AI Companion: Which AI Meeting Assistant is Better for Your Meetings? | Otter.ai</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p class="text-size-medium">Otter AI vs Zoom AI – compare Otter and Zoom AI Companion to find the best AI meeting assistant. Discover how each tool boosts productivity and efficiency.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Richard Tasker</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/communication-plan" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/6862764df567286dc308599c_685dc6e20dfae06652324756_676475a0549b4735351f100d_communication-plan%252520.jpeg" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="#" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="#" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p class="text-size-medium">Creating an Effective Communication Plan, With Examples</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p class="text-size-medium">Effective communication doesn’t happen by chance — it’s planned and nurtured. A communication plan fosters collaboration and keeps everyone informed.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/project-management-skills" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills.jpeg" loading="lazy" data-cover-img="" alt="" sizes="100vw" srcset="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-500.jpeg 500w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-800.jpeg 800w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-1080.jpeg 1080w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-1600.jpeg 1600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-2000.jpeg 2000w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-2600.jpeg 2600w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills-p-3200.jpeg 3200w, https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/685dc71359cdf5c43183485b_676385568da2e406af231f7c_project-management-skills.jpeg 4000w" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="#" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="#" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p class="text-size-medium">14 Essential Project Management Skills for Success</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p class="text-size-medium">Project managers juggle resources, teams, and shifting objectives. Here are 14 project management skills to push your goals from concept to completion.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Simon Lau</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div><div role="listitem" class="blog_d-related-collection-item w-dyn-item"><div class="blog_d-related-card"><a href="/2025/2025-blog/7-best-practices-for-using-online-collaboration-tools" class="blog_d-related-card_visual w-inline-block"><img src="https://cdn.prod.website-files.com/61a05ff14c09ecacc06eec05/6862763fcc91c932b32b2e68_685dc6d1d5c6609466ff8062_67b4e0904f6b06f5f13555ae_Online%252520Collaboration%252520Tools.jpeg" loading="lazy" data-cover-img="" alt="" class="img-cover"/></a><div class="blog_d-related-card_bottom"><div class="blog_d-related-card_bottom-inner"><a href="#" class="blog_d-hero-tag w-inline-block"><div class="text-size-small">Productivity Hacks</div></a><a href="#" class="blog_d-related-title-link w-inline-block"><div class="text-style-2lines"><div class="text-weight-medium"><p class="text-size-medium">9 Top Online Collaboration Tools in 2025</p></div></div></a><div class="text-style-2lines"><div class="text-color-muted"><p class="text-size-medium">Discover the best online collaboration tools to enhance your team’s productivity, and learn how to use them effectively.</p></div></div></div><div class="blog_d-hero-head_author-wrap_bottom"><div class="text-size-medium">Darius Contractor</div><div class="blog_d-hero-head_author-dot w-condition-invisible"></div><div class="blog_d-hero-head_author-read w-condition-invisible"><div class="icon-embed-small w-embed"><svg width="100%" height="100%" viewBox="0 0 24 25" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M18.25 13.5C18.25 16.9518 15.4518 19.75 12 19.75C8.54822 19.75 5.75 16.9518 5.75 13.5C5.75 10.0482 8.54822 7.25 12 7.25C15.4518 7.25 18.25 10.0482 18.25 13.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M16.5 9L17.25 8.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 7V5.25M12 5.25H9.75M12 5.25H14.25" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
<path d="M12 10.25V13.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
</svg></div><div class="w-embed"><p class="text-size-medium"> min</p></div></div></div></div></div></div></div></div></div></div></div></div></section><section class="section_footer"><div class="padding-global is-full-width"><div class="container-large"><div class="footer_container"><a href="/meeting-agent" class="footer-logo w-inline-block"><div class="footer-logo-embed w-embed"><svg width="100%" height="100%" viewBox="0 0 80 32" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
<path fill-rule="evenodd" clip-rule="evenodd" d="M51.4596 0.432373C53.8478 0.432373 55.7839 2.36844 55.7839 4.7567V26.8108C55.7839 29.199 53.8478 31.1351 51.4596 31.1351C49.0713 31.1351 47.1353 29.199 47.1353 26.8108V4.7567C47.1353 2.36844 49.0713 0.432373 51.4596 0.432373Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M39.3512 0.432373C41.7394 0.432373 43.6755 2.36844 43.6755 4.7567V26.8108C43.6755 29.199 41.7394 31.1351 39.3512 31.1351C36.9629 31.1351 35.0269 29.199 35.0269 26.8108V4.7567C35.0269 2.36844 36.9629 0.432373 39.3512 0.432373Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M63.5675 10.3784C65.9557 10.3784 67.8918 12.3145 67.8918 14.7027V17.2973C67.8918 19.6856 65.9557 21.6217 63.5675 21.6217C61.1792 21.6217 59.2432 19.6856 59.2432 17.2973V14.7027C59.2432 12.3145 61.1792 10.3784 63.5675 10.3784Z" fill="currentColor"/>
<path fill-rule="evenodd" clip-rule="evenodd" d="M75.6759 6.05396C78.0641 6.05396 80.0002 7.99002 80.0002 10.3783V21.1891C80.0002 23.5773 78.0641 25.5134 75.6759 25.5134C73.2876 25.5134 71.3516 23.5773 71.3516 21.1891V10.3783C71.3516 7.99002 73.2876 6.05396 75.6759 6.05396Z" fill="currentColor"/>
<path d="M15.7996 23.281C19.9967 23.281 23.3992 19.8786 23.3992 15.6814C23.3992 11.4843 19.9967 8.08183 15.7996 8.08183C11.6024 8.08183 8.19998 11.4843 8.19998 15.6814C8.19998 19.8786 11.6024 23.281 15.7996 23.281ZM15.7838 31.5676C7.06664 31.5676 0 24.5009 0 15.7838C0 7.06664 7.06664 0 15.7838 0C24.5009 0 31.5676 7.06664 31.5676 15.7838C31.5676 24.5009 24.5009 31.5676 15.7838 31.5676Z" fill="currentColor"/>
</svg></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67d05cb02024219f508f42aa_otter-footer-hover%402x.png" loading="lazy" alt="" class="footer-logo-gradient"/></a><div class="footer_column-container"><div class="footer_column"><div class="text-weight-medium"><p class="text-size-regular">AI Agents</p></div><ul role="list" class="footer-item-list"><li class="footer-item"><a underline-link="" href="/sales-agent" class="footer-link">Sales Agent</a></li><li class="footer-item"><a underline-link="" href="/recruiting-agent" class="footer-link">Recruiting Agent</a></li><li class="footer-item"><a underline-link="" href="/education-agent" class="footer-link">Education Agent<br/></a></li><li class="footer-item"><a underline-link="" href="/media-agent" class="footer-link">Media Agent</a></li></ul></div><div class="footer_column"><div class="text-weight-medium"><p class="text-size-regular">Resources</p></div><ul role="list" class="footer-item-list"><li class="footer-item"><a underline-link="" href="https://help.otter.ai/hc/en-us?_gl=1*1djb34*_ga*Nzk4MjYxNDczLjE2OTc3NDYzNDY.*_ga_F0G9HT49XE*MTc0MjgxNTU4Mi40NS4xLjE3NDI4MjQzMzguNTguMC45NzA2ODY5MTI.*_ga_718GRVQGD7*MTc0MjgxNTU4Mi40NS4xLjE3NDI4MjQzMzguNjAuMC45NTU5ODQ3Mjc." class="footer-link">Help Center</a></li><li class="footer-item"><a underline-link="" href="/2025/careers" class="footer-link">Careers</a></li><li class="footer-item"><a underline-link="" href="/2025/press" class="footer-link">Press<br/></a></li><li class="footer-item"><a underline-link="" href="/2025/blog" class="footer-link">Blog</a></li></ul></div><div class="footer_column"><div class="text-weight-medium"><p class="text-size-regular">Download</p></div><ul role="list" class="footer-item-list"><li class="footer-item"><a underline-link="" href="https://apps.apple.com/us/app/otter-voice-meeting-notes/id1276437113" class="footer-link">iOS app</a></li><li class="footer-item"><a underline-link="" href="https://play.google.com/store/apps/details?id=com.aisense.otter" class="footer-link">Android app</a></li><li class="footer-item"><a underline-link="" href="https://chrome.google.com/webstore/detail/otterai-transcribe-record/bnmojkbbkkonlmlfgejehefjldooiedp" class="footer-link">Chrome extention<br/></a></li></ul></div><div class="footer_column"><div class="text-weight-medium"><p class="text-size-regular">Social</p></div><ul role="list" class="footer-item-list"><li class="footer-item"><a underline-link="" href="https://www.linkedin.com/company/otter-ai/mycompany/" target="_blank" class="footer-link">LinkedIn</a></li><li class="footer-item"><a underline-link="" href="https://www.youtube.com/@Otterai" target="_blank" class="footer-link">YouTube</a></li><li class="footer-item"><a underline-link="" href="https://twitter.com/otter_ai" target="_blank" class="footer-link">X</a></li></ul></div><div id="w-node-b35a1f07-e681-cc26-b38c-adc535c852c4-35c8526b" class="footer_bottom"><a underline-link="" href="/meeting-agent" class="footer-link">© 2025 Otter.ai Inc</a><a underline-link="" href="/2025/privacy-policy" class="footer-link">Privacy policy</a><a underline-link="" href="/2025/terms-of-service" class="footer-link">Terms of service</a><a underline-link="" href="/software-services-agreement" class="footer-link">Software service agreement</a><a underline-link="" href="/jp" class="footer-link">JP</a><a id="cookie-settings" underline-link="" href="#" class="footer-link">Cookie settings</a></div></div></div></div></div><img src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/67d04d720978961f84fc5300_5e483ca0425acaa261ab6dce33dbcceb_otter-footer.svg" loading="lazy" alt="" class="footer-letters"/></section></div><script src="https://d3e54v103j8qbb.cloudfront.net/js/jquery-3.5.1.min.dc5e7f18c8.js?site=618e9316785b3582a5178502" type="text/javascript" integrity="sha256-9/aliU8dGd2tb6OSsuzixeV4y/faTqgFtohetphbbj0=" crossorigin="anonymous"></script><script src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/js/otterai-website.schunk.36b8fb49256177c8.js" type="text/javascript"></script><script src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/js/otterai-website.schunk.4809c84b7290f66f.js" type="text/javascript"></script><script src="https://cdn.prod.website-files.com/618e9316785b3582a5178502/js/otterai-website.29e7ea26.6055c4c4ef9a5973.js" type="text/javascript"></script><!-- Cookie Disabled Check -->
<script>
    if (!navigator.cookieEnabled) {
      document.body.innerHTML = `
        <div style="min-height: 80vh;display: flex; align-items: center; justify-content: center; padding: 3rem;">
          <p style="max-width: 42rem;font-size:2rem;text-align: center">Cookies are used in order to make Otter.ai website and applications work. To continue using Otter.ai, please enable cookies in your browser.</p>
        </div>
      `;
    }
  </script>
  
  <!-- Disable Scroll when Menu Opens -->
  <script>
  document.addEventListener('DOMContentLoaded', ()=>{
   document.querySelectorAll('.menu-button').forEach(trigger => {
    trigger.addEventListener('click', function(){ 
      if(!document.querySelector('body').classList.contains('overflow')){ 
        document.querySelectorAll('body').forEach(target => target.classList.add('overflow'));
      }
      else{ 
        document.querySelectorAll('body').forEach(target => target.classList.remove('overflow'));
      } 
    });
   });
   document.querySelectorAll('.nav__dropdown-link').forEach(trigger => {
    trigger.addEventListener('click', function(){ 
      document.querySelectorAll('body').forEach(target => target.classList.remove('overflow')); 
    });
   });
  });
  </script>
  
  <!-- Floating Menu -->
  <script>
  document.addEventListener('DOMContentLoaded', () => {
   document.querySelectorAll('.nav__trigger').forEach(trigger => { 
      new IntersectionObserver((entries, observer) => { 
        entries.forEach(entry => {
          if(entry.isIntersecting){
          document.querySelectorAll('.navbar').forEach(target => target.classList.remove('floating'));
        }
        else{
          document.querySelectorAll('.navbar').forEach(target => target.classList.add('floating'));
       }
        });
      },
      { 
        threshold: 0 
      }).observe(trigger);
     });
  });
  </script>
  
  <!-- Binding Amplitude tracking events -->
  <script type="text/javascript">

  /** retrieves the event properties associated with the redesign for tracking */
  function getHomeCohortEventProperties() {
    try {
      if (!window.getHomepageExperimentCohort) return {};
      const cohort = window.getHomepageExperimentCohort()
      if (!cohort) return {};
      return { HomePageVariant: cohort };
    } catch (e) {
      return {};
    }
  }

  function onClickAmplitudeTracking(event) {
    const el = event.currentTarget;
    const trackingType = el.dataset.trackingType;
  
    switch (trackingType) {
      case 'button':
      default:
        const homeCohortProperties = getHomeCohortEventProperties();
        amplitude.track('General_ButtonAction', {
          UIElementID: `${el.textContent ? el.textContent.slice(0, 48) : ''}|${
            el.className ? el.className : ''
          }|${el.href ? el.href : ''}`,
          ...homeCohortProperties
        });
        break;
    }
  }
  
  const elements = document.querySelectorAll('a');
  
  for (const el of elements) {
    el.addEventListener('click', onClickAmplitudeTracking);
  }
  </script>
  <!-- End binding Amplitude tracking events -->
  
  <noscript>
      <img src="https://ws.zoominfo.com/pixel/61f17c824827d70015787576" width="1" height="1" style="display: none;" alt="websights"/>
  </noscript>
  
  <style>
  #ot-sdk-btn.ot-sdk-show-settings, #ot-sdk-btn.optanon-show-settings{
    transition-property: border-color, color;
    transition-duration: 250ms, 250ms;
    transition-timing-function: cubic-bezier(.215, .61, .355, 1), cubic-bezier(.215, .61, .355, 1);
    font-size: 1rem;
    line-height: 1.3;
    font-weight: 600;
    letter-spacing: 0.16rem;
    text-decoration: none;
    text-transform: uppercase;
    color: white;
    border: none;
    height: auto;
    white-space: normal;
    word-wrap: break-word;
    padding: 0;
    background: transparent;
  }
  #ot-sdk-btn.ot-sdk-show-settings:hover, #ot-sdk-btn.optanon-show-settings:hover {
    color: #52d0f0;
    background: transparent;
  }
  </style>
  
  <script>
    $('#cookie-settings').on('click', function () {
      OneTrust.ToggleInfoDisplay();
    });
  </script>
  
  <!-- swiper 8 JS -->
  <script src="https://cdn.jsdelivr.net/npm/swiper@8/swiper-bundle.min.js"></script>
  
  <!-- Swiper Logic -->
  <script>
    let swipers = {};
    let windowWidth = window.innerWidth;
    let uniqueIdCounter = 0;
  
    const createResponsiveSwiper = (
      componentSelector,
      swiperSelector,
      classSelector,
      options,
      mode
    ) => {
      const mobile = window.matchMedia('(min-width: 0px) and (max-width: 991px)');
      const desktop = window.matchMedia('(min-width: 992px)');
  
      let elements = $(componentSelector);
  
      if (elements.length === 0) {
        console.log('No elements found for selector', componentSelector); // Step 2
        return;
      }
  
      elements.each(function () {
        // Generate a unique key for this instance
        let uniqueKey = classSelector + '_' + uniqueIdCounter;
  
        const arrows = '.swiper-arrow';
        const pagination = '.swiper-navigation';
  
        $(this).find(swiperSelector).addClass(uniqueKey);
        $(this).find(arrows).addClass(uniqueKey);
        $(this).find(pagination).addClass(uniqueKey);
  
        let swiperOptions = Object.assign({}, options, {
          navigation: {
            prevEl: `${arrows}.prev.${uniqueKey}`,
            nextEl: `${arrows}.next.${uniqueKey}`,
          },
        });
  
        swipers[classSelector] = swipers[classSelector] || {};
        swipers[classSelector][uniqueKey] = swipers[classSelector][uniqueKey] || {};
  
        let existingInstance = swipers[classSelector] ? swipers[classSelector][uniqueKey] : null;
  
        let shouldInitDesktop = mode === 'desktop' && desktop.matches;
        let shouldInitMobile = mode === 'mobile' && mobile.matches;
        let shouldInitAll = mode === 'all';
  
        let existingSwiper =
            swipers[classSelector] && swipers[classSelector][uniqueKey]
        ? swipers[classSelector][uniqueKey].swiperInstance
        : null;
        let existingMode =
            swipers[classSelector] && swipers[classSelector][uniqueKey]
        ? swipers[classSelector][uniqueKey].mode
        : null;
  
        if (shouldInitDesktop || shouldInitMobile || shouldInitAll) {
          if (!existingSwiper) {
            // Initialize new instance
            let swiper = new Swiper(`${swiperSelector}.${uniqueKey}`, swiperOptions);
  
            swipers[classSelector][uniqueKey] = {
              swiperInstance: swiper,
              mode: shouldInitDesktop ? 'desktop' : shouldInitMobile ? 'mobile' : 'all',
              initialized: true, // set the initialized flag to true
            };
  
            console.log('Swiper initialized for', componentSelector, 'with uniqueKey', uniqueKey);
          }
        } else if (existingSwiper) {
          // If none of the init conditions are true and an existing swiper instance is found, destroy it
          existingSwiper.destroy(true, true);
          delete swipers[classSelector][uniqueKey];
          console.log('Swiper destroyed for', componentSelector, 'with uniqueKey', uniqueKey);
        }
  
        // Increment the uniqueIdCounter after processing each element
        uniqueIdCounter++;
      });
    };
  
    // Function to initialize swipers from an array of instances
    const runSwipers = (swiperInstances) => {
      swiperInstances.forEach((instance) => {
        console.log(...instance);
        createResponsiveSwiper(...instance);
      });
    };
  
    const initSwipers = (swiperInstances) => {
      // Load
      window.addEventListener('load', function () {
        runSwipers(swiperInstances);
      });
  
      // Resize
      window.addEventListener('resize', function () {
        if (window.innerWidth !== windowWidth) {
          windowWidth = window.innerWidth;
          uniqueIdCounter = 0; // Reset the uniqueIdCounter
          runSwipers(swiperInstances);
        }
      });
    };
  
  </script>

<!-- Koala Pixel -->
<script>
!function(t){var k="ko",i=(window.globalKoalaKey=window.globalKoalaKey||k);if(window[i])return;var ko=(window[i]=[]);["identify","track","removeListeners","on","off","qualify","ready"].forEach(function(t){ko[t]=function(){var n=[].slice.call(arguments);return n.unshift(t),ko.push(n),ko}});var n=document.createElement("script");n.async=!0,n.setAttribute("src","https://cdn.getkoala.com/v1/pk_5342da8365de7d16955e1cd68a3f01d23fb0/sdk.js"),(document.body || document.head).appendChild(n)}();
</script><!-- Truncated headings and subheadings - Graphite IL API -->
<script>
  document.addEventListener("DOMContentLoaded", function() {
    // Obtener y truncar los headings a 73 caracteres
    var headingElements = document.querySelectorAll('[data-maxchars-heading]');
    
    headingElements.forEach(function(el) {
      var maxChars = 73; // Fijamos el número de caracteres a 73 para los headings
      var originalText = el.innerHTML.trim();
      
      if (originalText.length > maxChars) {
        var truncatedText = originalText.substring(0, maxChars) + '...';
        el.innerHTML = truncatedText;
      }
    });

    // Obtener y truncar los subheadings a 80 caracteres
    var subheadingElements = document.querySelectorAll('[data-maxchars-subheading]');
    
    subheadingElements.forEach(function(el) {
      var maxChars = 80; // Fijamos el número de caracteres a 80 para los subheadings
      var originalText = el.innerHTML.trim();
      
      if (originalText.length > maxChars) {
        var truncatedText = originalText.substring(0, maxChars) + '...';
        el.innerHTML = truncatedText;
      }
    });
  });
</script></body></html>
    """
    
    markdown_content = clean_html_text_and_convert_to_markdown(html, remove_links=True)
    
    print(markdown_content)
    import ipdb; ipdb.set_trace()


