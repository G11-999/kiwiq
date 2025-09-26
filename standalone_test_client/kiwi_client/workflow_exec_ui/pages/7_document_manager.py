"""
Document Manager: CRUD operations for customer data documents.
Provides a clean interface for querying, creating, updating, and deleting documents.
"""

import json
import uuid
from typing import Any, Dict, Optional, Union
import asyncio

import streamlit as st
from code_editor import code_editor

st.set_page_config(page_title="Document Manager", page_icon="📄", layout="wide")

from kiwi_client.workflow_exec_ui.utils.workflow_utils import custom_btns
from kiwi_client.workflow_exec_ui.utils.streamlit_runner import (
    get_customer_data_client_sync,
    run_async_operation_sync,
    upload_files_sync,
    validate_upload_config_sync
)
import kiwi_client.schemas.workflow_api_schemas as wf_schemas


def _render_header() -> None:
    """Render the page header with description."""
    st.title("📄 Document Manager")
    st.caption("Query, create, update, and delete customer data documents")
    
    with st.expander("ℹ️ About Document Identifiers", expanded=False):
        st.markdown("""
        **Document Identifiers:**
        - **Namespace**: Category/folder for the document (e.g., `invoices`, `user_profiles`)
        - **Document Name**: Unique name within the namespace (e.g., `invoice_001`, `john_doe`)
        - **Is Shared**: Whether document is shared across organization (default: False = user-specific)
        - **Is System Entity**: Whether document is stored in system paths (default: False = org-specific)
        
        **Document Types:**
        - **Versioned**: Maintains history, supports multiple versions
        - **Unversioned**: Simple key-value storage, latest data only
        """)


def _render_document_query_section() -> None:
    """Render the document query section."""
    st.subheader("🔍 Query Document")
    
    with st.form("query_document_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            query_namespace = st.text_input("Namespace", key="query_namespace", help="e.g., user_profiles, invoices")
            query_docname = st.text_input("Document Name", key="query_docname", help="e.g., john_doe, invoice_001")
        
        with col2:
            query_is_shared = st.checkbox("Is Shared", key="query_is_shared", help="Shared across organization")
            query_is_system = st.checkbox("Is System Entity", key="query_is_system", help="System-level document")
            query_version = st.text_input("Version (optional)", key="query_version", help="Specific version for versioned docs")
        
        query_submitted = st.form_submit_button("🔍 Query Document", type="primary")
    
    if query_submitted and query_namespace and query_docname:
        _handle_document_query(query_namespace, query_docname, query_is_shared, query_is_system, query_version)


def _handle_document_query(namespace: str, docname: str, is_shared: bool, is_system: bool, version: Optional[str]) -> None:
    """Handle document query operation."""
    with st.spinner("Querying document..."):
        try:
            client = get_customer_data_client_sync()
            
            # Try versioned first, then unversioned
            versioned_doc = run_async_operation_sync(
                client.get_versioned_document(
                    namespace=namespace,
                    docname=docname,
                    is_shared=is_shared,
                    version=version,
                    is_system_entity=is_system
                )
            )
            
            if versioned_doc:
                st.success("✅ Found versioned document!")
                _display_document_details(versioned_doc, is_versioned=True)
                
                # Store in session state for editing
                st.session_state['current_doc'] = {
                    'namespace': namespace,
                    'docname': docname,
                    'is_shared': is_shared,
                    'is_system_entity': is_system,
                    'is_versioned': True,
                    'data': versioned_doc.data,
                    'version': versioned_doc.version,
                    'created_at': versioned_doc.created_at.isoformat() if versioned_doc.created_at else None,
                    'updated_at': versioned_doc.updated_at.isoformat() if versioned_doc.updated_at else None
                }
            else:
                # Try unversioned
                unversioned_doc = run_async_operation_sync(
                    client.get_unversioned_document(
                        namespace=namespace,
                        docname=docname,
                        is_shared=is_shared,
                        is_system_entity=is_system
                    )
                )
                
                if unversioned_doc:
                    st.success("✅ Found unversioned document!")
                    _display_document_details(unversioned_doc, is_versioned=False)
                    
                    # Store in session state for editing
                    st.session_state['current_doc'] = {
                        'namespace': namespace,
                        'docname': docname,
                        'is_shared': is_shared,
                        'is_system_entity': is_system,
                        'is_versioned': False,
                        'data': unversioned_doc.data,
                        'created_at': unversioned_doc.created_at.isoformat() if unversioned_doc.created_at else None,
                        'updated_at': unversioned_doc.updated_at.isoformat() if unversioned_doc.updated_at else None
                    }
                else:
                    st.error("❌ Document not found")
                    # Clear current doc from session
                    if 'current_doc' in st.session_state:
                        del st.session_state['current_doc']
                        
        except Exception as e:
            st.error(f"❌ Error querying document: {e}")
            if 'current_doc' in st.session_state:
                del st.session_state['current_doc']


def _display_document_details(doc: Union[wf_schemas.CustomerDataRead, wf_schemas.CustomerDataUnversionedRead], is_versioned: bool) -> None:
    """Display document details in a clean format."""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 Document Data")
        
        # Display data based on type
        if isinstance(doc.data, dict):
            st.json(doc.data)
        else:
            st.code(str(doc.data), language="text")
    
    with col2:
        st.subheader("ℹ️ Metadata")
        
        metadata_info = {
            "Type": "Versioned" if is_versioned else "Unversioned",
            "Created": doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "Unknown",
            "Updated": doc.updated_at.strftime("%Y-%m-%d %H:%M:%S") if doc.updated_at else "Unknown"
        }
        
        if is_versioned and hasattr(doc, 'version'):
            metadata_info["Version"] = doc.version or "No version"
            metadata_info["Is Active"] = getattr(doc, 'is_active_version', 'Unknown')
        
        for key, value in metadata_info.items():
            st.metric(label=key, value=str(value))


def _render_document_create_update_section() -> None:
    """Render the document create/update section."""
    st.subheader("✏️ Create/Update Document")
    
    # Check if we have a current document loaded
    current_doc = st.session_state.get('current_doc')
    
    if current_doc:
        st.info(f"📝 Editing: `{current_doc['namespace']}/{current_doc['docname']}` ({'Versioned' if current_doc['is_versioned'] else 'Unversioned'})")
        
        # Pre-populate form with current document data
        default_namespace = current_doc['namespace']
        default_docname = current_doc['docname']
        default_is_shared = current_doc['is_shared']
        default_is_system = current_doc['is_system_entity']
        default_is_versioned = current_doc['is_versioned']
        default_data = json.dumps(current_doc['data'], indent=2) if isinstance(current_doc['data'], dict) else str(current_doc['data'])
    else:
        # Default values for new document
        default_namespace = ""
        default_docname = ""
        default_is_shared = False
        default_is_system = False
        default_is_versioned = False
        default_data = '{\n  "key": "value",\n  "example": true\n}'
    
    with st.form("create_update_document_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            cu_namespace = st.text_input("Namespace", value=default_namespace, key="cu_namespace")
            cu_docname = st.text_input("Document Name", value=default_docname, key="cu_docname")
            cu_is_shared = st.checkbox("Is Shared", value=default_is_shared, key="cu_is_shared")
        
        with col2:
            cu_is_system = st.checkbox("Is System Entity", value=default_is_system, key="cu_is_system")
            cu_is_versioned = st.checkbox("Is Versioned", value=default_is_versioned, key="cu_is_versioned")
            cu_version = st.text_input("Version Name (versioned only)", key="cu_version", help="Leave empty for default/active version")
        
        st.subheader("📝 Document Data")
        
        # Data input options
        data_input_mode = st.radio("Data Input Mode", ["JSON Editor", "Text Input"], horizontal=True)
        
        if data_input_mode == "JSON Editor":
            cu_data_editor = code_editor(
                code=default_data,
                lang="json",
                theme="default",
                height=300,
                response_mode="blur",
                allow_reset=True,
                buttons=custom_btns,
                key="cu_data_editor"
            )
            cu_data_raw = cu_data_editor.get("text", default_data)
        else:
            cu_data_raw = st.text_area("Document Data", value=default_data, height=200, key="cu_data_textarea")
        
        col_submit, col_clear = st.columns([1, 1])
        
        with col_submit:
            cu_submitted = st.form_submit_button("💾 Save Document", type="primary")
        
        with col_clear:
            cu_clear = st.form_submit_button("🗑️ Clear Form")
    
    if cu_clear:
        # Clear current document from session
        if 'current_doc' in st.session_state:
            del st.session_state['current_doc']
        st.rerun()
    
    if cu_submitted and cu_namespace and cu_docname and cu_data_raw:
        _handle_document_create_update(cu_namespace, cu_docname, cu_is_shared, cu_is_system, cu_is_versioned, cu_version, cu_data_raw)


def _handle_document_create_update(namespace: str, docname: str, is_shared: bool, is_system: bool, is_versioned: bool, version: Optional[str], data_raw: str) -> None:
    """Handle document create/update operation."""
    with st.spinner("Saving document..."):
        try:
            client = get_customer_data_client_sync()
            
            # Parse data
            parsed_data = _parse_document_data(data_raw)
            if parsed_data is None:
                return
            
            if is_versioned:
                # Check if document exists to determine create vs update
                existing_doc = run_async_operation_sync(
                    client.get_versioned_document(
                        namespace=namespace,
                        docname=docname,
                        is_shared=is_shared,
                        is_system_entity=is_system
                    )
                )
                
                if existing_doc:
                    # Update existing versioned document
                    update_data = wf_schemas.CustomerDataVersionedUpdate(
                        is_shared=is_shared,
                        data=parsed_data,
                        version=version if version else None,
                        is_system_entity=is_system
                    )
                    result = run_async_operation_sync(
                        client.update_versioned_document(namespace, docname, update_data)
                    )
                    if result:
                        st.success("✅ Versioned document updated successfully!")
                        _display_document_details(result, is_versioned=True)
                    else:
                        st.error("❌ Failed to update versioned document")
                else:
                    # Create new versioned document
                    init_data = wf_schemas.CustomerDataVersionedInitialize(
                        is_shared=is_shared,
                        initial_data=parsed_data,
                        initial_version=version if version else "v1.0",
                        is_system_entity=is_system
                    )
                    result = run_async_operation_sync(
                        client.initialize_versioned_document(namespace, docname, init_data)
                    )
                    if result:
                        st.success("✅ Versioned document created successfully!")
                        _display_document_details(result, is_versioned=True)
                    else:
                        st.error("❌ Failed to create versioned document")
            else:
                # Unversioned document (create or update)
                create_data = wf_schemas.CustomerDataUnversionedCreateUpdate(
                    is_shared=is_shared,
                    data=parsed_data,
                    is_system_entity=is_system
                )
                result = run_async_operation_sync(
                    client.create_or_update_unversioned_document(namespace, docname, create_data)
                )
                if result:
                    st.success("✅ Unversioned document saved successfully!")
                    _display_document_details(result, is_versioned=False)
                else:
                    st.error("❌ Failed to save unversioned document")
                    
        except Exception as e:
            st.error(f"❌ Error saving document: {e}")


def _parse_document_data(data_raw: str) -> Optional[Any]:
    """Parse document data from string input."""
    try:
        # Try to parse as JSON first
        parsed_data = json.loads(data_raw)
        return parsed_data
    except json.JSONDecodeError:
        # If JSON parsing fails, treat as primitive string
        # But first check if it looks like a number or boolean
        data_stripped = data_raw.strip()
        
        # Try boolean
        if data_stripped.lower() in ('true', 'false'):
            return data_stripped.lower() == 'true'
        
        # Try integer
        try:
            if '.' not in data_stripped:
                return int(data_stripped)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(data_stripped)
        except ValueError:
            pass
        
        # Default to string
        return data_raw


def _render_document_delete_section() -> None:
    """Render the document delete section."""
    current_doc = st.session_state.get('current_doc')
    
    if not current_doc:
        st.info("ℹ️ Query a document first to enable deletion")
        return
    
    st.subheader("🗑️ Delete Document")
    
    st.warning(f"⚠️ This will permanently delete: `{current_doc['namespace']}/{current_doc['docname']}`")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("🗑️ Delete Document", type="secondary"):
            _handle_document_delete(current_doc)
    
    with col2:
        if st.button("❌ Cancel", type="primary"):
            st.info("Delete operation cancelled")


def _handle_document_delete(doc_info: Dict[str, Any]) -> None:
    """Handle document deletion."""
    with st.spinner("Deleting document..."):
        try:
            client = get_customer_data_client_sync()
            
            if doc_info['is_versioned']:
                success = run_async_operation_sync(
                    client.delete_versioned_document(
                        namespace=doc_info['namespace'],
                        docname=doc_info['docname'],
                        is_shared=doc_info['is_shared'],
                        is_system_entity=doc_info['is_system_entity']
                    )
                )
            else:
                success = run_async_operation_sync(
                    client.delete_unversioned_document(
                        namespace=doc_info['namespace'],
                        docname=doc_info['docname'],
                        is_shared=doc_info['is_shared'],
                        is_system_entity=doc_info['is_system_entity']
                    )
                )
            
            if success:
                st.success("✅ Document deleted successfully!")
                # Clear current document from session
                if 'current_doc' in st.session_state:
                    del st.session_state['current_doc']
                st.rerun()
            else:
                st.error("❌ Failed to delete document")
                
        except Exception as e:
            st.error(f"❌ Error deleting document: {e}")


def _render_document_list_section() -> None:
    """Render the document listing section."""
    st.subheader("📋 List Documents")
    
    with st.form("list_documents_form"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            list_namespace = st.text_input("Namespace Filter (optional)", key="list_namespace")
            list_include_shared = st.checkbox("Include Shared", value=True, key="list_include_shared")
        
        with col2:
            list_include_user = st.checkbox("Include User-Specific", value=True, key="list_include_user")
            list_include_system = st.checkbox("Include System Entities", value=False, key="list_include_system")
        
        with col3:
            list_limit = st.number_input("Limit", min_value=1, max_value=1000, value=50, key="list_limit")
            list_skip = st.number_input("Skip", min_value=0, value=0, key="list_skip")
        
        list_submitted = st.form_submit_button("📋 List Documents", type="primary")
    
    if list_submitted:
        _handle_document_list(list_namespace, list_include_shared, list_include_user, list_include_system, list_limit, list_skip)


def _handle_document_list(namespace_filter: Optional[str], include_shared: bool, include_user: bool, include_system: bool, limit: int, skip: int) -> None:
    """Handle document listing operation."""
    with st.spinner("Loading documents..."):
        try:
            client = get_customer_data_client_sync()
            
            documents = run_async_operation_sync(
                client.list_documents(
                    namespace=namespace_filter if namespace_filter else None,
                    include_shared=include_shared,
                    include_user_specific=include_user,
                    skip=skip,
                    limit=limit,
                    include_system_entities=include_system
                )
            )
            
            if documents:
                st.success(f"✅ Found {len(documents)} documents")
                
                # Display documents in a table
                if len(documents) > 0:
                    # Create table data
                    table_data = []
                    for doc in documents:
                        table_data.append({
                            "Namespace": doc.namespace,
                            "Document Name": doc.docname,
                            "Type": "Versioned" if doc.is_versioned else "Unversioned",
                            "Shared": "✅" if doc.is_shared else "❌",
                            "System": "✅" if doc.is_system_entity else "❌",
                            "Created": doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else "Unknown",
                            "Updated": doc.updated_at.strftime("%Y-%m-%d %H:%M") if doc.updated_at else "Unknown"
                        })
                    
                    st.dataframe(table_data, use_container_width=True)
                    
                    # Add quick query buttons
                    st.subheader("🔍 Quick Query")
                    cols = st.columns(min(len(documents), 5))  # Max 5 columns
                    
                    for i, doc in enumerate(documents[:5]):  # Show first 5 documents
                        with cols[i]:
                            if st.button(f"Query {doc.docname[:15]}...", key=f"quick_query_{i}"):
                                # Set form values and trigger query
                                st.session_state['query_namespace'] = doc.namespace
                                st.session_state['query_docname'] = doc.docname
                                st.session_state['query_is_shared'] = doc.is_shared
                                st.session_state['query_is_system'] = doc.is_system_entity
                                st.rerun()
            else:
                st.info("ℹ️ No documents found matching the criteria")
                
        except Exception as e:
            st.error(f"❌ Error listing documents: {e}")


def _render_file_upload_section() -> None:
    """Render the file upload section."""
    st.subheader("📁 Upload Files")
    
    # File upload widget
    uploaded_files = st.file_uploader(
        "Choose files to upload",
        accept_multiple_files=True,
        help="Select one or more files to upload as documents. Supports various formats (PDF, DOCX, TXT, etc.)"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} file(s) selected")
        
        # Display selected files
        with st.expander("📄 Selected Files", expanded=True):
            for file in uploaded_files:
                st.write(f"• **{file.name}** ({file.size:,} bytes)")
        
        # Configuration section
        st.subheader("⚙️ Upload Configuration")
        
        # Global configuration
        with st.expander("🌐 Global Configuration", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                global_namespace = st.text_input("Namespace", value="uploaded_files", key="global_namespace", help="Category/folder for uploaded files")
                global_save_as_raw = st.checkbox("Save as Raw Binary", key="global_save_as_raw", help="Save files as binary data instead of converting to markdown")
                global_is_shared = st.checkbox("Shared Documents", key="global_is_shared", help="Make documents accessible to all users in organization")
            
            with col2:
                global_is_versioned = st.checkbox("Versioned Documents", key="global_is_versioned", help="Create versioned documents with history tracking")
                global_is_system = st.checkbox("System Entity", key="global_is_system", help="Create system-level documents (superuser only)")
                global_mode = st.selectbox("Upload Mode", ["upsert", "create"], key="global_mode", help="upsert: create or update, create: fail if exists")
        
        # Versioned configuration (only if versioned is enabled)
        versioned_config = None
        if st.session_state.get("global_is_versioned", False):
            with st.expander("📚 Versioned Configuration", expanded=True):
                version_name = st.text_input("Version Name", key="version_name", help="Leave empty for default version")
                is_complete = st.checkbox("Mark as Complete", key="is_complete", help="Mark uploaded documents as complete")
                
                versioned_config = wf_schemas.FileUploadVersionedConfig(
                    version=version_name if version_name else None,
                    is_complete=is_complete
                )
        
        # Per-file configuration (optional)
        file_specific_configs = {}
        if st.checkbox("🔧 Enable Per-File Configuration", help="Configure individual files differently"):
            with st.expander("📝 Per-File Settings", expanded=True):
                selected_file = st.selectbox("Select File to Configure", [f.name for f in uploaded_files])
                
                if selected_file:
                    st.subheader(f"Configuration for: {selected_file}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        file_namespace = st.text_input("Namespace Override", key=f"file_namespace_{selected_file}")
                        file_docname = st.text_input("Document Name Override", key=f"file_docname_{selected_file}")
                        file_description = st.text_area("Description", key=f"file_description_{selected_file}")
                    
                    with col2:
                        file_save_raw = st.checkbox("Save as Raw", key=f"file_save_raw_{selected_file}")
                        file_is_shared = st.checkbox("Shared", key=f"file_shared_{selected_file}")
                        file_is_versioned = st.checkbox("Versioned", key=f"file_versioned_{selected_file}")
                    
                    if st.button(f"Save Config for {selected_file}"):
                        # Build file-specific config
                        file_config = wf_schemas.FileUploadConfig(
                            namespace=file_namespace if file_namespace else global_namespace,
                            docname=file_docname if file_docname else None,
                            description=file_description if file_description else None,
                            is_shared=file_is_shared,
                            is_versioned=file_is_versioned,
                            save_as_raw=file_save_raw,
                            mode=wf_schemas.FileUploadModeEnum(global_mode),
                            versioned_config=versioned_config if file_is_versioned else None
                        )
                        file_specific_configs[selected_file] = file_config
                        st.success(f"✅ Configuration saved for {selected_file}")
        
        # Upload buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("🔍 Validate Configuration", type="secondary"):
                _handle_upload_validation(uploaded_files, global_namespace, global_save_as_raw, global_is_shared, 
                                        global_is_versioned, global_is_system, global_mode, versioned_config, file_specific_configs)
        
        with col2:
            if st.button("📤 Upload Files", type="primary"):
                _handle_file_upload(uploaded_files, global_namespace, global_save_as_raw, global_is_shared,
                                  global_is_versioned, global_is_system, global_mode, versioned_config, file_specific_configs)
        
        with col3:
            if st.button("🗑️ Clear Selection"):
                st.rerun()


def _handle_upload_validation(uploaded_files, namespace, save_as_raw, is_shared, is_versioned, is_system, mode, versioned_config, file_specific_configs):
    """Handle upload configuration validation."""
    try:
        # Build global config
        global_config = wf_schemas.FileUploadConfig(
            namespace=namespace,
            is_shared=is_shared,
            is_versioned=is_versioned,
            is_system_entity=is_system,
            save_as_raw=save_as_raw,
            mode=wf_schemas.FileUploadModeEnum(mode),
            versioned_config=versioned_config if is_versioned else None
        )
        
        # Build payload
        payload = wf_schemas.FileUploadRequestPayload(
            global_defaults=global_config,
            file_configs=file_specific_configs
        )
        
        # Create validation request
        validation_request = wf_schemas.FileUploadValidationRequest(
            payload=payload,
            files=[f.name for f in uploaded_files]
        )
        
        # Validate
        with st.spinner("Validating configuration..."):
            result = validate_upload_config_sync(validation_request)
            
            if result:
                if result.is_valid:
                    st.success("✅ Configuration is valid!")
                else:
                    st.error("❌ Configuration validation failed")
                    
                    if result.global_errors:
                        st.subheader("Global Errors:")
                        for error in result.global_errors:
                            st.error(f"• {error}")
                    
                    if result.file_errors:
                        st.subheader("File-Specific Errors:")
                        for filename, errors in result.file_errors.items():
                            st.error(f"**{filename}:**")
                            for error in errors:
                                st.error(f"  • {error}")
            else:
                st.error("❌ Validation request failed")
                
    except Exception as e:
        st.error(f"❌ Error during validation: {e}")


def _handle_file_upload(uploaded_files, namespace, save_as_raw, is_shared, is_versioned, is_system, mode, versioned_config, file_specific_configs):
    """Handle file upload operation."""
    try:
        # Prepare files for upload
        files_to_upload = []
        for uploaded_file in uploaded_files:
            # Read file content
            file_content = uploaded_file.read()
            content_type = uploaded_file.type or "application/octet-stream"
            
            files_to_upload.append((uploaded_file.name, file_content, content_type))
            
            # Reset file pointer for potential re-use
            uploaded_file.seek(0)
        
        # Build global config
        global_config = wf_schemas.FileUploadConfig(
            namespace=namespace,
            is_shared=is_shared,
            is_versioned=is_versioned,
            is_system_entity=is_system,
            save_as_raw=save_as_raw,
            mode=wf_schemas.FileUploadModeEnum(mode),
            versioned_config=versioned_config if is_versioned else None
        )
        
        # Build payload
        payload = wf_schemas.FileUploadRequestPayload(
            global_defaults=global_config,
            file_configs=file_specific_configs
        )
        
        # Upload files
        with st.spinner("Uploading files..."):
            results = upload_files_sync(files_to_upload, payload)
            
            if results:
                st.success(f"✅ Upload completed! Processed {len(results)} files.")
                
                # Display results
                for result in results:
                    filename = result.get("filename", "Unknown")
                    status = result.get("status", "unknown")
                    message = result.get("message", "No message")
                    
                    if status == "success":
                        st.success(f"**{filename}:** {message}")
                        
                        # Show document identifier if available
                        doc_id = result.get("document_identifier")
                        if doc_id:
                            with st.expander(f"📄 Document Details: {filename}"):
                                st.json(doc_id)
                    else:
                        st.error(f"**{filename}:** {message}")
            else:
                st.error("❌ Upload failed")
                
    except Exception as e:
        st.error(f"❌ Error during upload: {e}")


def main() -> None:
    """Main function to render the document manager page."""
    _render_header()
    
    # Create tabs for different operations
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 Query", "✏️ Create/Update", "🗑️ Delete", "📋 List", "📁 Upload"])
    
    with tab1:
        _render_document_query_section()
    
    with tab2:
        _render_document_create_update_section()
    
    with tab3:
        _render_document_delete_section()
    
    with tab4:
        _render_document_list_section()
    
    with tab5:
        _render_file_upload_section()


if __name__ == "__main__":
    main()
