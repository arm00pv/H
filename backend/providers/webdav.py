import requests
from typing import List, Dict, Any
from .base import BaseProvider
import xml.etree.ElementTree as ET

class WebDAVProvider(BaseProvider):
    def list_files(self) -> List[Dict[str, Any]]:
        url = self.config.get("url")
        username = self.config.get("username")
        password = self.config.get("password")

        if not url or not username or not password:
            raise ValueError("Missing WebDAV credentials")

        # Ensure URL ends with /
        if not url.endswith("/"):
            url += "/"

        headers = {
            "Depth": "1" # List children
        }

        response = requests.request("PROPFIND", url, auth=(username, password), headers=headers)
        if response.status_code not in [200, 207]:
            raise Exception(f"WebDAV Error: {response.status_code}")

        # Parse XML response
        # Note: This is a simplified parser. Real WebDAV XML can be complex with namespaces.
        files = []
        try:
            root = ET.fromstring(response.content)
            # Namespace handling is tricky in ElementTree with wildcards, so we strip or handle generically
            # Commonly 'd:response'

            namespaces = {'d': 'DAV:'}

            for response_node in root.findall('.//d:response', namespaces):
                href = response_node.find('.//d:href', namespaces).text
                propstat = response_node.find('.//d:propstat', namespaces)
                if propstat:
                    prop = propstat.find('.//d:prop', namespaces)
                    if prop:
                        # Get displayname or fallback to href basename
                        displayname = prop.find('.//d:displayname', namespaces)
                        name = displayname.text if displayname is not None else href.rstrip('/').split('/')[-1]

                        # Skip current directory
                        if href.endswith('/') and name == "":
                            continue

                        # Get content length
                        getcontentlength = prop.find('.//d:getcontentlength', namespaces)
                        size = int(getcontentlength.text) if getcontentlength is not None else 0

                        # Get content type
                        getcontenttype = prop.find('.//d:getcontenttype', namespaces)
                        content_type = getcontenttype.text if getcontenttype is not None else None

                        # Filter out directories if they don't have size or are clearly dirs
                        resourcetype = prop.find('.//d:resourcetype', namespaces)
                        is_collection = resourcetype is not None and resourcetype.find('.//d:collection', namespaces) is not None

                        if not is_collection:
                            files.append({
                                "filename": name,
                                "size": size,
                                "content_type": content_type,
                                "external_id": href # href is essentially the ID
                            })
        except Exception as e:
            print(f"Error parsing WebDAV XML: {e}")
            # Fallback or re-raise?
            # For MVP let's just return what we got
            pass

        return files

    def download_file(self, external_id: str):
        url = self.config.get("url")
        username = self.config.get("username")
        password = self.config.get("password")

        # Construct full URL if external_id is relative or full path
        # Usually href in WebDAV is path absolute from root of server, e.g. /remote.php/webdav/file.txt
        # Our URL might be https://server/remote.php/webdav/
        # We need to be careful about joining.

        # Simplistic approach: If external_id starts with http, use it.
        # If it starts with /, assume it's path on the server.
        # But we authenticated against 'url'.

        # Let's assume external_id (href) is the path component.
        # We need the base domain from 'url'.

        from urllib.parse import urlparse, urljoin

        parsed_base = urlparse(url)
        # If external_id is already a full URL, use it
        if external_id.startswith("http"):
            full_url = external_id
        else:
            # Combine scheme://netloc with external_id (which is path)
            base = f"{parsed_base.scheme}://{parsed_base.netloc}"
            full_url = urljoin(base, external_id)

        with requests.get(full_url, auth=(username, password), stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                yield chunk
