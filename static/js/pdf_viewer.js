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
            <div class="text-center py-8">
                <svg class="w-8 h-8 mx-auto mb-2 text-red-500/60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
                <p class="text-red-400 text-sm">加载失败，请刷新页面重试</p>
            </div>
        `;
    }
}

// 渲染文件列表
function renderFileList(files, isFiltered = false) {
    const fileList = document.getElementById('fileList');

    if (!files || files.length === 0) {
        fileList.innerHTML = `
            <div class="text-center text-gray-500 py-8">
                <svg class="w-8 h-8 mx-auto mb-2 text-arena-red/40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"/>
                </svg>
                暂无PDF文件
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
        const displayName = file.display_name || file.filename;

        html += `
            <div class="file-item p-3 ${index === 0 ? 'active' : ''}"
                 data-filepath="${file.path}"
                 onclick="selectPDFFileByPath('${file.path}')">
                <div class="flex items-center justify-between">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center mb-1">
                            <svg class="w-4 h-4 text-arena-red flex-shrink-0 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
                            </svg>
                            <span class="text-white text-sm font-semibold truncate">${displayName}</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-arena-red text-xs font-bold">${file.year}年</span>
                            <span class="text-gray-500 text-xs">${file.size}</span>
                        </div>
                    </div>
                    <svg class="w-4 h-4 text-gray-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                    </svg>
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
    document.querySelectorAll('.file-item').forEach(item => {
        item.classList.remove('active');
    });
    const activeItem = document.querySelector(`.file-item[data-filepath="${filePath}"]`);
    if (activeItem) activeItem.classList.add('active');
    
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
        const noPreview = document.getElementById('noPreview');
        noPreview.innerHTML = `
            <svg class="w-16 h-16 mb-4 text-red-500/60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
            </svg>
            <h5 class="text-lg font-semibold mb-2 text-red-400">加载失败</h5>
            <p class="text-gray-500">${error.message}</p>
            <p class="text-gray-600 text-xs mt-1">文件路径: ${file.path}</p>
            <button class="btn-primary text-white px-4 py-2 text-xs font-bold mt-4" onclick="selectPDFFile(0)">
                重新加载
            </button>
        `;
        noPreview.style.display = 'flex';
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
            yearButtons.forEach(btn => {
                btn.classList.remove('active', 'btn-primary');
                btn.classList.add('btn-outline');
            });
            this.classList.remove('btn-outline');
            this.classList.add('active', 'btn-primary');

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
    const existingAlert = document.querySelector('.alert-toast');
    if (existingAlert) {
        existingAlert.remove();
    }

    let bgColor, borderColor;
    switch (type) {
        case 'success':
            bgColor = 'rgba(34, 197, 94, 0.1)';
            borderColor = 'rgba(34, 197, 94, 0.3)';
            break;
        case 'error': case 'danger':
            bgColor = 'rgba(239, 68, 68, 0.1)';
            borderColor = 'rgba(239, 68, 68, 0.3)';
            break;
        case 'warning':
            bgColor = 'rgba(245, 158, 11, 0.1)';
            borderColor = 'rgba(245, 158, 11, 0.3)';
            break;
        default:
            bgColor = 'rgba(230, 0, 0, 0.1)';
            borderColor = 'rgba(230, 0, 0, 0.3)';
    }

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert-toast fixed top-5 right-5 z-50';
    alertDiv.style.cssText = `
        background: ${bgColor};
        border: 1px solid ${borderColor};
        clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
        min-width: 300px;
        padding: 1rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    `;

    alertDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:0.75rem;">
            <span style="color:white">${message}</span>
            <button type="button" style="color:#9CA3AF;font-size:1.25rem;margin-left:auto;background:none;border:none;cursor:pointer;line-height:1;" onclick="this.parentElement.parentElement.remove()">&times;</button>
        </div>
    `;

    document.body.appendChild(alertDiv);

    // 4秒后自动消失
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 4000);
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
