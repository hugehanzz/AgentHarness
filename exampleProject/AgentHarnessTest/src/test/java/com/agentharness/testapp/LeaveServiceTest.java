package com.agentharness.testapp;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LeaveServiceTest {
    private final LeaveService service = new LeaveService();

    @Test
    void createsDraftLeaveApplication() {
        LeaveApplication application = service.create("leave-1", "emp-1", 2, "family event");

        assertEquals("leave-1", application.getId());
        assertEquals("emp-1", application.getEmployeeId());
        assertEquals(2, application.getDays());
        assertEquals("family event", application.getReason());
        assertEquals(LeaveStatus.DRAFT, application.getStatus());
    }

    @Test
    void approvesLeaveThroughHappyPath() {
        LeaveApplication application = service.create("leave-1", "emp-1", 3, "annual leave");

        service.submit(application);
        service.approveByManager(application);
        service.approveByHr(application);
        service.archive(application);

        assertEquals(LeaveStatus.ARCHIVED, application.getStatus());
    }

    @Test
    void rejectsSubmittedLeaveAndArchivesIt() {
        LeaveApplication application = service.create("leave-2", "emp-2", 1, "appointment");

        service.submit(application);
        service.reject(application);
        service.archive(application);

        assertEquals(LeaveStatus.ARCHIVED, application.getStatus());
    }

    @Test
    void rejectsInvalidTransition() {
        LeaveApplication application = service.create("leave-3", "emp-3", 1, "travel");

        InvalidLeaveTransitionException exception = assertThrows(
            InvalidLeaveTransitionException.class,
            () -> service.approveByHr(application)
        );
        assertEquals("Invalid leave transition: DRAFT -> HR_APPROVED", exception.getMessage());
    }

    @Test
    void rejectsInvalidApplicationInput() {
        IllegalArgumentException exception = assertThrows(
            IllegalArgumentException.class,
            () -> service.create("leave-4", "emp-4", 0, "bad input")
        );
        assertEquals("days must be greater than zero", exception.getMessage());
    }

    @Test
    void printsDjhNbMessage() {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        PrintStream originalOut = System.out;
        try {
            System.setOut(new PrintStream(output));

            System.out.println("djhnb");
        } finally {
            System.setOut(originalOut);
        }

        assertEquals("djhnb" + System.lineSeparator(), output.toString());
    }

    @Test
    void printsPrimeNumbersWithinOneHundred() {
        List<Integer> primes = new ArrayList<Integer>();
        for (int number = 2; number <= 100; number++) {
            if (isPrime(number)) {
                primes.add(number);
            }
        }

        System.out.println(primes);

        assertEquals(Arrays.asList(
            2, 3, 5, 7, 11, 13, 17, 19, 23, 29,
            31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
            73, 79, 83, 89, 97
        ), primes);
    }

    @Test
    void printsPalindromeNumbersUnder1000() {
        List<Integer> palindromes = new ArrayList<Integer>();
        for (int number = 1; number < 1000; number++) {
            if (isPalindrome(number)) {
                palindromes.add(number);
            }
        }

        System.out.println(palindromes);

        assertEquals(Arrays.asList(
            1, 2, 3, 4, 5, 6, 7, 8, 9,
            11, 22, 33, 44, 55, 66, 77, 88, 99,
            101, 111, 121, 131, 141, 151, 161, 171, 181, 191,
            202, 212, 222, 232, 242, 252, 262, 272, 282, 292,
            303, 313, 323, 333, 343, 353, 363, 373, 383, 393,
            404, 414, 424, 434, 444, 454, 464, 474, 484, 494,
            505, 515, 525, 535, 545, 555, 565, 575, 585, 595,
            606, 616, 626, 636, 646, 656, 666, 676, 686, 696,
            707, 717, 727, 737, 747, 757, 767, 777, 787, 797,
            808, 818, 828, 838, 848, 858, 868, 878, 888, 898,
            909, 919, 929, 939, 949, 959, 969, 979, 989, 999
        ), palindromes);
    }

    @Test
    void printsThreeLineStarTriangle() {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        PrintStream originalOut = System.out;
        try {
            System.setOut(new PrintStream(output));

            System.out.println("*");
            System.out.println("***");
            System.out.println("*****");
        } finally {
            System.setOut(originalOut);
        }

        String expected = "*" + System.lineSeparator()
            + "***" + System.lineSeparator()
            + "*****" + System.lineSeparator();
        assertEquals(expected, output.toString());
    }

    @Test
    void sortsRandomNaturalNumbersWithBubbleSort() {
        Random random = new Random();
        int[] numbers = new int[10];
        for (int i = 0; i < numbers.length; i++) {
            numbers[i] = random.nextInt(101);
        }

        System.out.println("Original random numbers: " + Arrays.toString(numbers));

        for (int i = 0; i < numbers.length - 1; i++) {
            for (int j = 0; j < numbers.length - i - 1; j++) {
                if (numbers[j] > numbers[j + 1]) {
                    int temp = numbers[j];
                    numbers[j] = numbers[j + 1];
                    numbers[j + 1] = temp;
                }
            }
        }

        System.out.println("Sorted random numbers: " + Arrays.toString(numbers));
        for (int i = 0; i < numbers.length - 1; i++) {
            assertTrue(numbers[i] <= numbers[i + 1]);
        }
    }

    @Test
    void quickSortRandomNaturalNumbersTest() {
        Random random = new Random();
        int[] numbers = new int[10];
        for (int i = 0; i < numbers.length; i++) {
            numbers[i] = random.nextInt(101);
        }
        int[] expected = Arrays.copyOf(numbers, numbers.length);
        Arrays.sort(expected);

        System.out.println("Original quick sort numbers: " + Arrays.toString(numbers));

        quickSort(numbers, 0, numbers.length - 1);

        System.out.println("Sorted quick sort numbers: " + Arrays.toString(numbers));
        assertEquals(10, numbers.length);
        assertArrayEquals(expected, numbers);
        for (int i = 0; i < numbers.length - 1; i++) {
            assertTrue(numbers[i] <= numbers[i + 1]);
        }
    }

    @Test
    void selectionSortRandomNaturalNumbersTest() {
        Random random = new Random();
        int[] numbers = new int[10];
        for (int i = 0; i < numbers.length; i++) {
            numbers[i] = random.nextInt(101);
        }
        int[] expected = Arrays.copyOf(numbers, numbers.length);
        Arrays.sort(expected);

        System.out.println("Original selection sort numbers: " + Arrays.toString(numbers));

        for (int i = 0; i < numbers.length - 1; i++) {
            int minimumIndex = i;
            for (int j = i + 1; j < numbers.length; j++) {
                if (numbers[j] < numbers[minimumIndex]) {
                    minimumIndex = j;
                }
            }
            swap(numbers, i, minimumIndex);
        }

        System.out.println("Sorted selection sort numbers: " + Arrays.toString(numbers));
        assertEquals(10, numbers.length);
        assertArrayEquals(expected, numbers);
        for (int i = 0; i < numbers.length - 1; i++) {
            assertTrue(numbers[i] <= numbers[i + 1]);
        }
    }

    @Test
    void printsMaximumNumberFromTwoRandomIntegers() {
        Random random = new Random();
        int[] numbers = new int[] {random.nextInt(101), random.nextInt(101)};
        //输出数组
        System.out.println("Random numbers: " + Arrays.toString(numbers));
        int maximum = Math.max(numbers[0], numbers[1]);

        System.out.println(maximum);

        assertTrue(maximum >= numbers[0]);
        assertTrue(maximum >= numbers[1]);
        assertTrue(maximum == numbers[0] || maximum == numbers[1]);
    }

    @Test
    void printsMinimumNumberFromTwoRandomIntegers() {
        Random random = new Random();
        int[] numbers = new int[] {random.nextInt(101), random.nextInt(101)};
        System.out.println("Random numbers: " + Arrays.toString(numbers));
        int minimum = Math.min(numbers[0], numbers[1]);

        System.out.println(minimum);

        assertTrue(minimum <= numbers[0]);
        assertTrue(minimum <= numbers[1]);
        assertTrue(minimum == numbers[0] || minimum == numbers[1]);
    }

    private boolean isPrime(int number) {
        if (number < 2) {
            return false;
        }
        for (int divisor = 2; divisor * divisor <= number; divisor++) {
            if (number % divisor == 0) {
                return false;
            }
        }
        return true;
    }

    private boolean isPalindrome(int number) {
        int original = number;
        int reversed = 0;
        while (number > 0) {
            reversed = reversed * 10 + number % 10;
            number = number / 10;
        }
        return original == reversed;
    }

    private void quickSort(int[] numbers, int left, int right) {
        if (left >= right) {
            return;
        }

        int pivotIndex = partition(numbers, left, right);
        quickSort(numbers, left, pivotIndex - 1);
        quickSort(numbers, pivotIndex + 1, right);
    }

    private int partition(int[] numbers, int left, int right) {
        int pivot = numbers[right];
        int smallerIndex = left - 1;

        for (int current = left; current < right; current++) {
            if (numbers[current] <= pivot) {
                smallerIndex++;
                swap(numbers, smallerIndex, current);
            }
        }

        swap(numbers, smallerIndex + 1, right);
        return smallerIndex + 1;
    }

    private void swap(int[] numbers, int first, int second) {
        int temp = numbers[first];
        numbers[first] = numbers[second];
        numbers[second] = temp;
    }
}
