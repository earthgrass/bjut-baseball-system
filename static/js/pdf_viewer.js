// PDF查看器全局变量
let pdfFiles = []; // 所有PDF文件
let currentDisplayedFiles = []; // 当前显示的文件列表（筛选后）
let currentPDF = null;
let currentZoom = 1.0;
const ZOOM_STEP = 0.1;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.0;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    loadPDFFiles();
    setupEventListeners();
});

// 加载PDF文件列表
async function loadPDFFiles() {
    try {
        const response = await fetch('/api/pdf/files');
        pdfFiles = await response.json();
        currentDisplayedFiles = [...pdfFiles]; // 初始显示所有文件
        
        console.log('加载的PDF文件列表:', pdfFiles);
        
        // 更新文件总数
        document.getElementById('totalFilesCount').textContent = pdfFiles.length;
        
        // 渲染文件列表
        renderFileList(currentDisplayedFiles);
        
    } catch (error) {
        console.error('加载PDF文件列表失败:', error);
        showAlert('加载PDF文件列表失败', 'danger');
        document.getElementById('fileList').innerHTML = `
            <div class="text-center text-danger py-4">
                <i class="fas fa-exclamation-triangle me-2"></i>加载失败，请刷新页面重试
            </div>
        `;
    }
}

// 渲染文件列表
function renderFileList(files, isFiltered = false) {
    const fileList = document.getElementById('fileList');
    
    if (!files || files.length === 0) {
        fileList.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="fas fa-folder-open me-2"></i>暂无PDF文件
            </div>
        `;
        return;
    }
    
    // 更新当前显示的文件列表
    if (isFiltered) {
        currentDisplayedFiles = files;
    }
    
    let html = '';
    
    files.forEach((file, index) => {
        // 从文件名中提取比赛信息
        const displayName = file.display_name || file.filename;
        
        html += `
            <div class="list-group-item file-list-item ${index === 0 ? 'active' : ''}" 
                 data-filepath="${file.path}" 
                 onclick="selectPDFFileByPath('${file.path}')">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="me-3">
                        <div class="d-flex align-items-center mb-1">
                            <i class="fas fa-file-pdf text-danger me-2"></i>
                            <strong class="text-truncate" style="max-width: 200px;">${displayName}</strong>
                        </div>
                        <div class="d-flex align-items-center">
                            <span class="badge year-badge bg-primary me-2">${file.year}年</span>
                            <span class="file-size">${file.size}</span>
                        </div>
                    </div>
                    <div>
                        <i class="fas fa-chevron-right text-muted"></i>
                    </div>
                </div>
            </div>
        `;
    });
    
    fileList.innerHTML = html;
    
    // 默认选择第一个文件
    if (files.length > 0) {
        selectPDFFileByPath(files[0].path);
    }
}

// 通过文件路径选择PDF文件
async function selectPDFFileByPath(filePath) {
    // 在当前显示的文件列表中查找文件
    const file = currentDisplayedFiles.find(f => f.path === filePath);
    if (!file) {
        console.error('未找到文件:', filePath);
        return;
    }
    
    currentPDF = file;
    
    // 更新活动状态
    document.querySelectorAll('.file-list-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`.file-list-item[data-filepath="${filePath}"]`).classList.add('active');
    
    // 更新当前文件名
    document.getElementById('currentFileName').textContent = file.display_name;
    
    // 显示PDF预览器
    document.getElementById('noPreview').style.display = 'none';
    document.getElementById('pdfViewer').style.display = 'block';
    document.getElementById('pdfInfo').style.display = 'block';
    
    // 更新文件信息
    updateFileInfo(file);
    
    // 加载PDF内容
    await loadPDFContent(file);
}

// 通过索引选择PDF文件（兼容旧代码）
async function selectPDFFile(index) {
    if (index < 0 || index >= currentDisplayedFiles.length) return;
    
    const file = currentDisplayedFiles[index];
    await selectPDFFileByPath(file.path);
}

// 更新文件信息
function updateFileInfo(file) {
    // 从文件名中提取比赛信息
    const filename = file.filename;
    const displayName = file.display_name || filename;
    
    // 尝试解析文件名中的比赛信息
    let matchup = displayName;
    let date = '未知日期';
    
    // 简单的解析逻辑：假设文件名格式为 "对阵双方_比赛日期"
    const parts = filename.replace('.pdf', '').split('_');
    if (parts.length >= 2) {
        // 最后一部分可能是日期
        const lastPart = parts[parts.length - 1];
        if (lastPart.match(/\d{4}/)) {
            date = lastPart;
            matchup = parts.slice(0, -1).join(' ');
        }
    }
    
    document.getElementById('infoFileName').textContent = filename;
    document.getElementById('infoYear').textContent = `${file.year}年`;
    document.getElementById('infoSize').textContent = file.size;
    document.getElementById('infoMatchup').textContent = matchup;
    document.getElementById('infoDate').textContent = date;
    document.getElementById('infoPath').textContent = file.path;
}

// 加载PDF内容
async function loadPDFContent(file) {
    try {
        console.log('加载PDF文件:', file);
        
        // 使用相对路径（如 '2024/北京工业大学_vs_中国人民公安大学_Nov_9_2024(1).pdf'）
        // 注意：file.path 现在已经是相对路径，不需要移除 'data/' 前缀
        const filePath = file.path;
        
        console.log('文件路径:', filePath);
        
        // 双重编码以确保中文路径正确传递
        const encodedPath = encodeURIComponent(filePath);
        
        console.log('编码后路径:', encodedPath);
        
        const response = await fetch(`/api/pdf/view/${encodedPath}`);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}: 加载PDF文件失败`);
        }
        
        const data = await response.json();
        
        if (data.content) {
            // 创建base64数据URL
            const pdfDataUrl = `data:application/pdf;base64,${data.content}`;
            
            // 更新iframe的src
            const pdfViewer = document.getElementById('pdfViewer');
            pdfViewer.src = pdfDataUrl;
            
            // 重置缩放
            currentZoom = 1.0;
            updateZoom();
            
            showAlert(`已加载: ${data.filename}`, 'success');
        } else {
            throw new Error('PDF内容为空');
        }
        
    } catch (error) {
        console.error('加载PDF内容失败:', error);
        console.error('文件信息:', file);
        
        showAlert(`加载PDF失败: ${error.message}`, 'danger');
        
        // 显示错误信息
        document.getElementById('noPreview').innerHTML = `
            <i class="fas fa-exclamation-triangle text-danger"></i>
            <h5 class="mt-3">加载失败</h5>
            <p class="text-muted">${error.message}</p>
            <p class="text-muted small">文件路径: ${file.path}</p>
            <button class="btn btn-sm btn-primary mt-2" onclick="selectPDFFile(0)">
                <i class="fas fa-redo me-2"></i>重新加载
            </button>
        `;
        document.getElementById('noPreview').style.display = 'flex';
        document.getElementById('pdfViewer').style.display = 'none';
    }
}

// 放大PDF
function zoomIn() {
    if (currentZoom < MAX_ZOOM) {
        currentZoom += ZOOM_STEP;
        updateZoom();
    }
}

// 缩小PDF
function zoomOut() {
    if (currentZoom > MIN_ZOOM) {
        currentZoom -= ZOOM_STEP;
        updateZoom();
    }
}

// 更新缩放
function updateZoom() {
    const pdfViewer = document.getElementById('pdfViewer');
    pdfViewer.style.transform = `scale(${currentZoom})`;
    pdfViewer.style.transformOrigin = 'top left';
    pdfViewer.style.width = `${100 / currentZoom}%`;
    pdfViewer.style.height = `${100 / currentZoom}%`;
}

// 下载当前PDF
function downloadCurrentPDF() {
    if (!currentPDF) {
        showAlert('请先选择一个PDF文件', 'warning');
        return;
    }
    
    try {
        // 构建文件路径
        const filePath = currentPDF.path.replace('data/', '');
        const downloadUrl = `/api/pdf/view/${encodeURIComponent(filePath)}`;
        
        // 创建下载链接
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = currentPDF.filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showAlert(`开始下载: ${currentPDF.filename}`, 'success');
        
    } catch (error) {
        console.error('下载PDF失败:', error);
        showAlert(`下载失败: ${error.message}`, 'danger');
    }
}

// 设置事件监听器
function setupEventListeners() {
    // 搜索功能
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', function() {
        filterFiles();
    });
    
    // 年份筛选
    const yearButtons = document.querySelectorAll('#yearFilter button');
    yearButtons.forEach(button => {
        button.addEventListener('click', function() {
            // 更新按钮状态
            yearButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // 筛选文件
            filterFiles();
        });
    });
}

// 筛选文件
function filterFiles() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const selectedYear = document.querySelector('#yearFilter .active').dataset.year;
    
    let filteredFiles = pdfFiles;
    
    // 按年份筛选
    if (selectedYear !== 'all') {
        filteredFiles = filteredFiles.filter(file => file.year === selectedYear);
    }
    
    // 按搜索词筛选
    if (searchTerm) {
        filteredFiles = filteredFiles.filter(file => {
            const filename = file.filename.toLowerCase();
            const displayName = file.display_name.toLowerCase();
            return filename.includes(searchTerm) || displayName.includes(searchTerm);
        });
    }
    
    // 渲染筛选后的文件列表
    renderFileList(filteredFiles, true); // 传递true表示是筛选后的列表
    
    // 更新文件总数显示
    document.getElementById('totalFilesCount').textContent = filteredFiles.length;
}

// 显示警告信息
function showAlert(message, type = 'info') {
    // 移除现有的警告
    const existingAlert = document.querySelector('.alert-dismissible');
    if (existingAlert) {
        existingAlert.remove();
    }
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // 3秒后自动消失
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 3000);
}

// 键盘快捷键支持
document.addEventListener('keydown', function(event) {
    // Ctrl + 加号: 放大
    if ((event.ctrlKey || event.metaKey) && (event.key === '+' || event.key === '=')) {
        event.preventDefault();
        zoomIn();
    }
    
    // Ctrl + 减号: 缩小
    if ((event.ctrlKey || event.metaKey) && event.key === '-') {
        event.preventDefault();
        zoomOut();
    }
    
    // Ctrl + F: 聚焦搜索框
    if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
        event.preventDefault();
        document.getElementById('searchInput').focus();
    }
    
    // 上下箭头: 切换文件
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault();
        navigateFiles(event.key === 'ArrowUp' ? -1 : 1);
    }
});

// 导航文件
function navigateFiles(direction) {
    const currentIndex = currentPDF ? currentDisplayedFiles.findIndex(file => file.path === currentPDF.path) : -1;
    
    if (currentIndex >= 0) {
        let newIndex = currentIndex + direction;
        
        // 循环导航
        if (newIndex < 0) newIndex = currentDisplayedFiles.length - 1;
        if (newIndex >= currentDisplayedFiles.length) newIndex = 0;
        
        selectPDFFile(newIndex);
    }
}

// 导出功能：供其他页面调用
window.PDFViewer = {
    loadPDFFiles,
    selectPDFFile,
    zoomIn,
    zoomOut,
    downloadCurrentPDF
};
