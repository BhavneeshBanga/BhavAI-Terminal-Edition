let currentInput = '0';
let previousInput = '';
let operation = null;
let shouldResetDisplay = false;

const display = document.querySelector('.display-text');
const buttons = document.querySelectorAll('.btn');

function updateDisplay() {
    display.textContent = currentInput;
}

function clearCalculator() {
    currentInput = '0';
    previousInput = '';
    operation = null;
    shouldResetDisplay = false;
    updateDisplay();
}

function inputNumber(num) {
    if (shouldResetDisplay || currentInput === '0') {
        currentInput = num;
        shouldResetDisplay = false;
    } else {
        currentInput += num;
    }
    updateDisplay();
}

function inputDecimal() {
    if (shouldResetDisplay) {
        currentInput = '0.';
        shouldResetDisplay = false;
    } else if (currentInput.indexOf('.') === -1) {
        currentInput += '.';
    }
    updateDisplay();
}

function performOperation(op) {
    if (operation && previousInput !== '') {
        calculate();
    }
    
    previousInput = currentInput;
    operation = op;
    shouldResetDisplay = true;
}

function calculate() {
    const prev = parseFloat(previousInput);
    const current = parseFloat(currentInput);
    let result;
    
    switch (operation) {
        case '+':
            result = prev + current;
            break;
        case '-':
            result = prev - current;
            break;
        case '×':
            result = prev * current;
            break;
        case '÷':
            result = current !== 0 ? prev / current : 'Error';
            break;
        default:
            return;
    }
    
    currentInput = String(result);
    operation = null;
    previousInput = '';
    shouldResetDisplay = false;
    updateDisplay();
}

function handlePercentage() {
    currentInput = String(parseFloat(currentInput) / 100);
    updateDisplay();
}

function handleToggleSign() {
    currentInput = String(parseFloat(currentInput) * -1);
    updateDisplay();
}

buttons.forEach(button => {
    button.addEventListener('click', () => {
        const value = button.getAttribute('data-value');
        
        switch (value) {
            case 'C':
                clearCalculator();
                break;
            case '±':
                handleToggleSign();
                break;
            case '%':
                handlePercentage();
                break;
            case '+':
            case '-':
            case '×':
            case '÷':
                performOperation(value);
                break;
            case '=':
                calculate();
                break;
            case '.':
                inputDecimal();
                break;
            default:
                if (!isNaN(value)) {
                    inputNumber(value);
                }
        }
    });
});

// Keyboard support
document.addEventListener('keydown', (e) => {
    const key = e.key;
    
    if (key >= '0' && key <= '9') {
        inputNumber(key);
    } else if (key === '.') {
        inputDecimal();
    } else if (key === '+' || key === '-' || key === '*' || key === '/') {
        performOperation(key);
    } else if (key === 'Enter' || key === '=') {
        calculate();
    } else if (key === 'Escape' || key === 'c' || key === 'C') {
        clearCalculator();
    }
});