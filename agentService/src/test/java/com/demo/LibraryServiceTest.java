```java
package com.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class LibraryServiceTest {

    @Mock
    private RestTemplate restTemplate;

    @InjectMocks
    private LibraryService libraryService;

    @BeforeEach
    void setup() {
        // Setup any common configurations or data here
    }

    @Test
    void testGetAvailableBooksSuccessfulResponse() {
        // Arrange
        String issueId = "ISSUE-123";
        String responseBody = "Book1,Book2,Book3";
        ResponseEntity<String> responseEntity = ResponseEntity.ok(responseBody);
        when(restTemplate.getForEntity(any(), any())).thenReturn(responseEntity);

        // Act
        List<String> availableBooks = libraryService.getAvailableBooks(issueId);

        // Assert
        assertEquals(3, availableBooks.size());
        assertTrue(availableBooks.contains("Book1"));
        assertTrue(availableBooks.contains("Book2"));
        assertTrue(availableBooks.contains("Book3"));
    }

    @Test
    void testGetAvailableBooksUnsuccessfulResponse() {
        // Arrange
        String issueId = "ISSUE-123";
        ResponseEntity<String> responseEntity = ResponseEntity.status(404).build();
        when(restTemplate.getForEntity(any(), any())).thenReturn(responseEntity);

        // Act
        List<String> availableBooks = libraryService.getAvailableBooks(issueId);

        // Assert
        assertTrue(availableBooks.isEmpty());
    }

    @Test
    void testGetAvailableBooksEmptyResponseBody() {
        // Arrange
        String issueId = "ISSUE-123";
        ResponseEntity<String> responseEntity = ResponseEntity.ok("");
        when(restTemplate.getForEntity(any(), any())).thenReturn(responseEntity);

        // Act
        List<String> availableBooks = libraryService.getAvailableBooks(issueId);

        // Assert
        assertEquals(1, availableBooks.size());
        assertTrue(availableBooks.contains(""));
    }
}
```